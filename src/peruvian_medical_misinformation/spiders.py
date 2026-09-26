"""Spiders de Scrapy para descubrir y extraer noticias públicas permitidas."""

from __future__ import annotations

import csv
import re
from datetime import date
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit

from dateutil import parser as date_parser

from .artifacts import append_log, write_jsonl
from .config import enabled_sources
from .corpus import (
    build_article_record,
    canonicalize_url,
    error_record,
    is_allowed_domain,
    save_versioned_html,
    utc_now,
)

try:  # El módulo solo se importa al ejecutar la recolección opcional.
    import scrapy
    from scrapy import signals
    from scrapy.downloadermiddlewares.retry import RetryMiddleware
    from twisted.internet import reactor
    from twisted.internet.task import deferLater
except ImportError as error:  # pragma: no cover - dependiente del extra scraping
    raise RuntimeError("Instala el extra de scraping: pip install -e '.[scraping]'") from error


DISCOVERY_FIELDS = [
    "url",
    "source_id",
    "source_dataset",
    "source_name",
    "discovery_method",
    "keyword_hint",
    "discovered_at",
]


class ExponentialBackoffRetryMiddleware(RetryMiddleware):
    """Aplica una pausa exponencial y acotada entre reintentos de Scrapy."""

    def __init__(self, settings: scrapy.settings.Settings) -> None:
        super().__init__(settings)
        self.backoff_base_seconds = max(0.0, settings.getfloat("RETRY_BACKOFF_BASE_SECONDS", 2.0))
        self.backoff_max_seconds = max(
            self.backoff_base_seconds,
            settings.getfloat("RETRY_BACKOFF_MAX_SECONDS", 30.0),
        )

    def _retry(self, request: scrapy.Request, reason: Any, spider: scrapy.Spider) -> Any:
        retry_request = super()._retry(request, reason, spider)
        if retry_request is None or self.backoff_base_seconds == 0:
            return retry_request
        retry_number = max(1, int(retry_request.meta.get("retry_times", 1)))
        delay = min(self.backoff_max_seconds, self.backoff_base_seconds * (2 ** (retry_number - 1)))
        spider.crawler.stats.inc_value("retry/backoff_seconds", delay)
        spider.logger.info("Reintento %s en %.1f s: %s", retry_number, delay, request.url)
        return deferLater(reactor, delay, lambda: retry_request)


def _looks_like_xml(response: scrapy.http.Response) -> bool:
    content_type = response.headers.get(b"Content-Type", b"").decode("latin-1").lower()
    return "xml" in content_type or response.url.casefold().endswith((".xml", ".rss"))


def _is_page_url(url: str) -> bool:
    path = urlsplit(url).path.casefold()
    return not path.endswith((".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".pdf", ".mp4", ".mp3"))


def _matches_keyword(url: str, anchor: str, keywords: Iterable[str]) -> bool:
    haystack = f"{url} {anchor}".casefold()
    return any(keyword.casefold() in haystack for keyword in keywords)


class SourceDiscoverySpider(scrapy.Spider):
    """Descubre URLs internas desde categorías, RSS, sitemaps o archivos públicos."""

    name = "medical_source_discovery"

    def __init__(
        self,
        *,
        sources_config: dict[str, Any],
        keywords: list[str],
        output_path: str,
        max_pages_per_source: int,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.sources = enabled_sources(sources_config)
        self.keywords = keywords
        self.output_path = Path(output_path)
        self.max_pages_per_source = max_pages_per_source
        self.pages_seen: dict[str, int] = {source_id: 0 for source_id in self.sources}
        self.discovered: dict[str, dict[str, str]] = {}

    @classmethod
    def from_crawler(cls, crawler: scrapy.crawler.Crawler, *args: Any, **kwargs: Any) -> "SourceDiscoverySpider":
        spider = super().from_crawler(crawler, *args, **kwargs)
        crawler.signals.connect(spider.closed, signal=signals.spider_closed)
        return spider

    def start_requests(self) -> Iterable[scrapy.Request]:
        for source_id, source in self.sources.items():
            discovery = source.get("discovery", {})
            entrypoints = discovery.get("entrypoints", []) if isinstance(discovery, dict) else []
            for entrypoint in entrypoints:
                if not isinstance(entrypoint, dict) or not entrypoint.get("url"):
                    continue
                url = str(entrypoint["url"]).strip()
                if not is_allowed_domain(url, source.get("allowed_domains", [])):
                    self.logger.warning("Entrada ignorada fuera del dominio permitido: %s", url)
                    continue
                yield scrapy.Request(
                    url,
                    callback=self.parse_entrypoint,
                    errback=self.handle_error,
                    meta={
                        "source_id": source_id,
                        "entrypoint": entrypoint,
                        "page_depth": 0,
                    },
                    dont_filter=False,
                )

    def parse_entrypoint(self, response: scrapy.http.Response) -> Iterable[scrapy.Request]:
        source_id = str(response.meta["source_id"])
        source = self.sources[source_id]
        entrypoint = response.meta["entrypoint"]
        self.pages_seen[source_id] += 1
        if self.pages_seen[source_id] > self.max_pages_per_source:
            return
        kind = str(entrypoint.get("kind", "category")).casefold()
        assume_health = bool(entrypoint.get("assume_health_section", False))
        if kind in {"sitemap", "rss", "atom"} or _looks_like_xml(response):
            links = response.xpath("//*[local-name()='loc' or local-name()='link']/text()").getall()
            for href in links:
                yield from self._handle_link(
                    response,
                    href,
                    "",
                    source_id,
                    source,
                    kind,
                    assume_health,
                    follow_sitemap=kind == "sitemap",
                )
            return

        for anchor in response.css("a[href]"):
            href = anchor.attrib.get("href", "")
            anchor_text = " ".join(anchor.css("::text").getall())
            yield from self._handle_link(
                response,
                href,
                anchor_text,
                source_id,
                source,
                kind,
                assume_health,
                follow_sitemap=False,
            )
        depth = int(response.meta.get("page_depth", 0))
        if depth < int(entrypoint.get("max_pages", 1)) - 1:
            next_page = response.css("link[rel='next']::attr(href), a[rel='next']::attr(href)").get()
            if next_page:
                next_url = response.urljoin(next_page)
                if is_allowed_domain(next_url, source.get("allowed_domains", [])):
                    yield scrapy.Request(
                        next_url,
                        callback=self.parse_entrypoint,
                        errback=self.handle_error,
                        meta={**response.meta, "page_depth": depth + 1},
                    )

    def _handle_link(
        self,
        response: scrapy.http.Response,
        href: str,
        anchor_text: str,
        source_id: str,
        source: dict[str, Any],
        method: str,
        assume_health: bool,
        *,
        follow_sitemap: bool,
    ) -> Iterable[scrapy.Request]:
        if not href:
            return []
        candidate = response.urljoin(href.strip())
        try:
            candidate = canonicalize_url(candidate)
        except ValueError:
            return []
        if not is_allowed_domain(candidate, source.get("allowed_domains", [])) or not _is_page_url(candidate):
            return []
        if follow_sitemap and candidate.casefold().endswith(".xml"):
            if int(response.meta.get("page_depth", 0)) < 1:
                return [
                    scrapy.Request(
                        candidate,
                        callback=self.parse_entrypoint,
                        errback=self.handle_error,
                        meta={**response.meta, "page_depth": int(response.meta.get("page_depth", 0)) + 1},
                    )
                ]
            return []
        if not assume_health and not _matches_keyword(candidate, anchor_text, self.keywords):
            return []
        self.discovered.setdefault(
            candidate,
            {
                "url": candidate,
                "source_id": source_id,
                "source_dataset": str(source.get("source_dataset", f"scraped_{source_id}")),
                "source_name": str(source.get("name", source_id)),
                "discovery_method": method,
                "keyword_hint": next(
                    (keyword for keyword in self.keywords if keyword.casefold() in f"{candidate} {anchor_text}".casefold()),
                    "health_section" if assume_health else "",
                ),
                "discovered_at": utc_now(),
            },
        )
        return []

    def handle_error(self, failure: Any) -> None:
        self.logger.warning("Error durante descubrimiento: %s", failure.getErrorMessage())

    def closed(self, reason: str) -> None:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        with self.output_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=DISCOVERY_FIELDS)
            writer.writeheader()
            writer.writerows(self.discovered[url] for url in sorted(self.discovered))
        self.logger.info("Descubrimiento finalizado (%s): %s URLs", reason, len(self.discovered))


class ArticleCollectionSpider(scrapy.Spider):
    """Descarga un manifiesto de URLs con Scrapy y preserva cada HTML obtenido."""

    name = "medical_article_collection"

    def __init__(
        self,
        *,
        sources_config: dict[str, Any],
        urls_file: str,
        output_path: str,
        log_path: str,
        metadata_path: str,
        raw_html_root: str,
        project_root: str,
        run_id: str,
        period_start: str,
        period_end: str,
        max_urls: int,
        minimum_body_characters: int = 240,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.sources = enabled_sources(sources_config)
        self.urls_file = Path(urls_file)
        self.output_path = Path(output_path)
        self.log_path = Path(log_path)
        self.metadata_path = Path(metadata_path)
        self.raw_html_root = Path(raw_html_root)
        self.project_root = Path(project_root).resolve()
        self.run_id = run_id
        self.period_start = date_parser.parse(period_start).date()
        self.period_end = date_parser.parse(period_end).date()
        self.max_urls = max_urls
        self.minimum_body_characters = max(1, int(minimum_body_characters))
        self.records: list[dict[str, Any]] = []

    @classmethod
    def from_crawler(cls, crawler: scrapy.crawler.Crawler, *args: Any, **kwargs: Any) -> "ArticleCollectionSpider":
        spider = super().from_crawler(crawler, *args, **kwargs)
        crawler.signals.connect(spider.closed, signal=signals.spider_closed)
        return spider

    def start_requests(self) -> Iterable[scrapy.Request]:
        with self.urls_file.open(newline="", encoding="utf-8-sig") as handle:
            rows = list(csv.DictReader(handle))
        submitted = 0
        seen: set[str] = set()
        for row in rows:
            source_id = str(row.get("source_id") or "").strip()
            url = str(row.get("url") or "").strip()
            if not url or source_id not in self.sources:
                continue
            source = self.sources[source_id]
            try:
                canonical_url = canonicalize_url(url)
            except ValueError:
                self.records.append(
                    error_record(
                        requested_url=url,
                        source_dataset=str(source.get("source_dataset", f"scraped_{source_id}")),
                        source_name=str(source.get("name", source_id)),
                        run_id=self.run_id,
                        reason="url_invalida",
                    )
                )
                continue
            if canonical_url in seen or not is_allowed_domain(canonical_url, source.get("allowed_domains", [])):
                continue
            seen.add(canonical_url)
            if self.max_urls and submitted >= self.max_urls:
                break
            submitted += 1
            yield scrapy.Request(
                canonical_url,
                callback=self.parse_article,
                errback=self.handle_error,
                meta={"source_id": source_id, "requested_url": url},
                dont_filter=False,
            )

    def parse_article(self, response: scrapy.http.Response) -> None:
        source_id = str(response.meta["source_id"])
        source = self.sources[source_id]
        requested_url = str(response.meta["requested_url"])
        source_dataset = str(source.get("source_dataset", f"scraped_{source_id}"))
        source_name = str(source.get("name", source_id))
        if response.status >= 400:
            self.records.append(
                error_record(
                    requested_url=requested_url,
                    source_dataset=source_dataset,
                    source_name=source_name,
                    run_id=self.run_id,
                    reason=f"http_{response.status}",
                    http_status=response.status,
                )
            )
            return
        record = build_article_record(
            html=response.text,
            requested_url=requested_url,
            response_url=response.url,
            source_dataset=source_dataset,
            source_name=source_name,
            allowed_domains=source.get("allowed_domains", []),
            http_status=response.status,
            run_id=self.run_id,
            minimum_body_characters=self.minimum_body_characters,
        )
        raw_path = save_versioned_html(
            response.text,
            raw_html_root=self.raw_html_root,
            source_dataset=source_dataset,
            article_record_id=str(record.get("record_id") or "unknown"),
            retrieved_at=str(record["retrieved_at"]),
        )
        try:
            record["raw_html_path"] = str(raw_path.resolve().relative_to(self.project_root))
        except ValueError:
            record["raw_html_path"] = str(raw_path)
        self._filter_period(record)
        self.records.append(record)

    def _filter_period(self, record: dict[str, Any]) -> None:
        published_at = str(record.get("published_at") or "")
        if not published_at:
            if record.get("extraction_status") == "valid":
                record.update(extraction_status="needs_review", exclusion_reason="fecha_publicacion_no_disponible")
            return
        try:
            published_day = date_parser.parse(published_at).date()
        except (TypeError, ValueError, OverflowError):
            record.update(extraction_status="needs_review", exclusion_reason="fecha_publicacion_no_normalizable")
            return
        if not self.period_start <= published_day <= self.period_end:
            record.update(extraction_status="excluded", exclusion_reason="fuera_del_periodo_configurado")

    def handle_error(self, failure: Any) -> None:
        request = failure.request
        source_id = str(request.meta.get("source_id", ""))
        source = self.sources.get(source_id, {})
        response = getattr(failure.value, "response", None)
        self.records.append(
            error_record(
                requested_url=str(request.meta.get("requested_url", request.url)),
                source_dataset=str(source.get("source_dataset", f"scraped_{source_id}")),
                source_name=str(source.get("name", source_id)),
                run_id=self.run_id,
                reason=failure.getErrorMessage(),
                http_status=getattr(response, "status", ""),
            )
        )

    def closed(self, reason: str) -> None:
        write_jsonl(self.output_path, self.records, append=True)
        write_jsonl(self.metadata_path, self.records)
        append_log(self.log_path, self.records)
        self.logger.info("Colección finalizada (%s): %s registros", reason, len(self.records))


def scrapy_settings(base_config: dict[str, Any], *, cache_dir: str) -> dict[str, Any]:
    collection = base_config.get("collection", {})
    return {
        "BOT_NAME": "peruvian_medical_misinformation",
        "ROBOTSTXT_OBEY": bool(collection.get("robots_txt_obey", True)),
        "USER_AGENT": str(collection.get("user_agent", "peruvian-medical-misinformation-research/0.2")),
        "DOWNLOAD_DELAY": float(collection.get("download_delay_seconds", 1.5)),
        "RANDOMIZE_DOWNLOAD_DELAY": True,
        "CONCURRENT_REQUESTS_PER_DOMAIN": int(collection.get("concurrent_requests_per_domain", 1)),
        "DOWNLOAD_TIMEOUT": int(collection.get("timeout_seconds", 30)),
        "RETRY_ENABLED": True,
        "RETRY_TIMES": int(collection.get("retry_times", 2)),
        "RETRY_BACKOFF_BASE_SECONDS": float(collection.get("retry_backoff_base_seconds", 2)),
        "RETRY_BACKOFF_MAX_SECONDS": float(collection.get("retry_backoff_max_seconds", 30)),
        "RETRY_HTTP_CODES": [408, 429, 500, 502, 503, 504],
        "HTTPCACHE_ENABLED": bool(collection.get("cache_enabled", True)),
        "HTTPCACHE_DIR": cache_dir,
        "HTTPCACHE_IGNORE_HTTP_CODES": [429, 500, 502, 503, 504],
        "CLOSESPIDER_PAGECOUNT": int(collection.get("max_urls_per_run", 300)),
        "DEPTH_LIMIT": 2,
        "HTTPERROR_ALLOW_ALL": True,
        "TELNETCONSOLE_ENABLED": False,
        "LOG_LEVEL": "INFO",
        "DOWNLOADER_MIDDLEWARES": {
            "scrapy.downloadermiddlewares.retry.RetryMiddleware": None,
            "peruvian_medical_misinformation.spiders.ExponentialBackoffRetryMiddleware": 550,
        },
    }
