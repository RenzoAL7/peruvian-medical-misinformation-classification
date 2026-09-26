"""Extracción, normalización y trazabilidad de noticias médicas públicas.

Este módulo amplía el prototipo ``collection.py`` sin eliminarlo. Los scripts
de fase 1 usan estas funciones para producir registros con el esquema completo.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup
from dateutil import parser as date_parser

try:
    import trafilatura
except ImportError:  # pragma: no cover - optional during unit tests
    trafilatura = None


TRACKING_PARAMETERS = {"fbclid", "gclid", "mc_cid", "mc_eid"}
MIN_BODY_CHARACTERS = 240

CORPUS_FIELDS = [
    "record_id",
    "source_dataset",
    "source_name",
    "url",
    "canonical_url",
    "retrieved_at",
    "published_at",
    "title",
    "subtitle_or_bajada",
    "body",
    "author",
    "section",
    "language",
    "http_status",
    "scraping_method",
    "raw_html_path",
    "content_hash",
    "normalized_text",
    "normalized_content_hash",
    "extraction_status",
    "exclusion_reason",
    "duplicate_status",
    "duplicate_of_record_id",
    "duplicate_similarity",
    "source_original_label",
    "source_row_id",
    "run_id",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonicalize_url(url: str) -> str:
    """Normaliza URL y elimina fragmentos y parámetros de seguimiento."""

    parsed = urlsplit(url.strip())
    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError("La URL debe usar HTTP o HTTPS")
    if not parsed.hostname:
        raise ValueError("La URL no contiene un dominio")
    hostname = parsed.hostname.lower().rstrip(".")
    netloc = hostname if parsed.port is None else f"{hostname}:{parsed.port}"
    query = sorted(
        (
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if key.lower() not in TRACKING_PARAMETERS and not key.lower().startswith("utm_")
        ),
        key=lambda pair: (pair[0], pair[1]),
    )
    return urlunsplit((parsed.scheme.lower(), netloc, parsed.path or "/", urlencode(query), ""))


def is_allowed_domain(url: str, allowed_domains: Iterable[str]) -> bool:
    hostname = (urlsplit(url).hostname or "").lower().rstrip(".")
    normalized = [domain.lower().lstrip(".").rstrip(".") for domain in allowed_domains]
    return any(hostname == domain or hostname.endswith(f".{domain}") for domain in normalized)


def record_id(canonical_url: str) -> str:
    return hashlib.sha256(canonical_url.encode("utf-8")).hexdigest()[:20]


def text_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def normalize_text(value: str) -> str:
    """Aplica NFKC y espacios consistentes, conservando tildes y negaciones."""

    normalized = unicodedata.normalize("NFKC", value or "").replace("\x00", "")
    return re.sub(r"\s+", " ", normalized).strip()


def model_text(title: str, subtitle: str, body: str) -> str:
    return normalize_text("\n\n".join(part.strip() for part in (title, subtitle, body) if part.strip()))


def detect_language(text: str) -> str:
    """Heurística conservadora para marcar textos que requieren revisión."""

    tokens = re.findall(r"[a-záéíóúüñ]+", text.casefold())
    if len(tokens) < 20:
        return "und"
    common_spanish = {
        "de", "la", "el", "en", "y", "que", "los", "las", "para", "con", "una", "un",
        "por", "del", "se", "no", "sin", "nunca", "salud", "como", "más", "sobre",
    }
    return "es" if sum(token in common_spanish for token in tokens) / len(tokens) >= 0.03 else "und"


def normalize_date(value: str) -> str:
    if not value:
        return ""
    try:
        return date_parser.parse(value).isoformat()
    except (TypeError, ValueError, OverflowError):
        return ""


def _meta_content(soup: BeautifulSoup, *names: str) -> str:
    for name in names:
        tag = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
        if tag and tag.get("content"):
            return str(tag["content"]).strip()
    return ""


def _jsonld_nodes(value: Any) -> Iterable[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        yield value
        for child in value.values():
            yield from _jsonld_nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from _jsonld_nodes(child)


def _jsonld_value(soup: BeautifulSoup, *keys: str) -> str:
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            payload = json.loads(script.string or script.get_text())
        except (TypeError, json.JSONDecodeError):
            continue
        for node in _jsonld_nodes(payload):
            for key in keys:
                value = node.get(key)
                if isinstance(value, Mapping):
                    value = value.get("name") or value.get("@id")
                elif isinstance(value, list):
                    value = ", ".join(
                        str(item.get("name", "")) if isinstance(item, Mapping) else str(item)
                        for item in value
                    )
                if value:
                    return str(value).strip()
    return ""


def extract_metadata(html: str, response_url: str = "") -> dict[str, str]:
    """Extrae título, bajada, autor, sección, fecha y canónica sin una plantilla fija."""

    soup = BeautifulSoup(html, "html.parser")
    canonical_tag = soup.find("link", attrs={"rel": lambda value: value and "canonical" in value})
    canonical_href = str(canonical_tag.get("href", "")).strip() if canonical_tag else ""
    canonical_url = urljoin(response_url, canonical_href) if canonical_href else response_url
    title = _meta_content(soup, "og:title", "twitter:title") or _jsonld_value(soup, "headline", "name")
    if not title and soup.title:
        title = soup.title.get_text(" ", strip=True)
    subtitle = _meta_content(soup, "og:description", "twitter:description", "description")
    author = _meta_content(soup, "article:author", "author") or _jsonld_value(soup, "author")
    section = _meta_content(soup, "article:section", "section") or _jsonld_value(soup, "articleSection")
    published = _meta_content(soup, "article:published_time", "datePublished", "pubdate", "date")
    if not published:
        published = _jsonld_value(soup, "datePublished", "dateCreated")
    if not published:
        time_tag = soup.find("time", attrs={"datetime": True})
        published = str(time_tag.get("datetime", "")).strip() if time_tag else ""
    return {
        "canonical_url": canonical_url,
        "title": normalize_text(title),
        "subtitle_or_bajada": normalize_text(subtitle),
        "author": normalize_text(author),
        "section": normalize_text(section),
        "published_at": normalize_date(published),
    }


def extract_body(html: str) -> tuple[str, str]:
    """Usa Trafilatura primero y BeautifulSoup como respaldo documentado."""

    if trafilatura is not None:
        extracted = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=False,
            include_links=False,
            favor_precision=True,
        )
        if extracted and len(normalize_text(extracted)) >= MIN_BODY_CHARACTERS:
            return normalize_text(extracted), "trafilatura"
    soup = BeautifulSoup(html, "html.parser")
    for element in soup(["script", "style", "noscript", "nav", "footer", "header", "aside", "form"]):
        element.decompose()
    root = soup.find("article") or soup.find("main") or soup
    paragraphs = [
        normalize_text(paragraph.get_text(" ", strip=True))
        for paragraph in root.find_all("p")
        if len(normalize_text(paragraph.get_text(" ", strip=True))) >= 40
    ]
    return "\n\n".join(paragraphs).strip(), "beautifulsoup_fallback"


def empty_record(*, url: str, source_dataset: str, source_name: str, run_id: str) -> dict[str, Any]:
    return {
        "record_id": "",
        "source_dataset": source_dataset,
        "source_name": source_name,
        "url": url.strip(),
        "canonical_url": "",
        "retrieved_at": utc_now(),
        "published_at": "",
        "title": "",
        "subtitle_or_bajada": "",
        "body": "",
        "author": "",
        "section": "",
        "language": "und",
        "http_status": "",
        "scraping_method": "",
        "raw_html_path": "",
        "content_hash": "",
        "normalized_text": "",
        "normalized_content_hash": "",
        "extraction_status": "pending",
        "exclusion_reason": "",
        "duplicate_status": "not_checked",
        "duplicate_of_record_id": "",
        "duplicate_similarity": "",
        "source_original_label": "",
        "source_row_id": "",
        "run_id": run_id,
    }


def build_article_record(
    *,
    html: str,
    requested_url: str,
    response_url: str,
    source_dataset: str,
    source_name: str,
    allowed_domains: Iterable[str],
    http_status: int | str,
    run_id: str,
    minimum_body_characters: int = MIN_BODY_CHARACTERS,
) -> dict[str, Any]:
    """Construye un registro completo; jamás infiere una etiqueta desde la fuente."""

    record = empty_record(
        url=requested_url,
        source_dataset=source_dataset,
        source_name=source_name,
        run_id=run_id,
    )
    record["http_status"] = http_status
    try:
        final_url = canonicalize_url(response_url)
        if not is_allowed_domain(final_url, allowed_domains):
            raise ValueError("La redirección terminó fuera del dominio permitido")
    except ValueError as error:
        record.update(extraction_status="excluded", exclusion_reason=str(error))
        return record
    metadata = extract_metadata(html, final_url)
    try:
        canonical_url = canonicalize_url(metadata["canonical_url"] or final_url)
    except ValueError:
        canonical_url = final_url
    if not is_allowed_domain(canonical_url, allowed_domains):
        record.update(
            canonical_url=final_url,
            record_id=record_id(final_url),
            extraction_status="needs_review",
            exclusion_reason="canonical_fuera_del_dominio_permitido",
        )
        return record
    body, method = extract_body(html)
    original_text = "\n\n".join(
        value for value in (metadata["title"], metadata["subtitle_or_bajada"], body) if value
    )
    normalized = model_text(metadata["title"], metadata["subtitle_or_bajada"], body)
    language = detect_language(normalized)
    status = "valid"
    reason = ""
    minimum_body_characters = max(1, int(minimum_body_characters))
    if not body:
        status, reason = "excluded", "contenido_vacio"
    elif len(body) < minimum_body_characters:
        status, reason = "excluded", "contenido_demasiado_corto"
    elif language != "es":
        status, reason = "needs_review", "idioma_no_confirmado_espanol"
    record.update(
        record_id=record_id(canonical_url),
        canonical_url=canonical_url,
        published_at=metadata["published_at"],
        title=metadata["title"],
        subtitle_or_bajada=metadata["subtitle_or_bajada"],
        body=body,
        author=metadata["author"],
        section=metadata["section"],
        language=language,
        scraping_method=method,
        content_hash=text_hash(original_text) if original_text else "",
        normalized_text=normalized,
        normalized_content_hash=text_hash(normalized) if normalized else "",
        extraction_status=status,
        exclusion_reason=reason,
    )
    return record


def error_record(
    *,
    requested_url: str,
    source_dataset: str,
    source_name: str,
    run_id: str,
    reason: str,
    http_status: int | str = "",
) -> dict[str, Any]:
    record = empty_record(
        url=requested_url,
        source_dataset=source_dataset,
        source_name=source_name,
        run_id=run_id,
    )
    record.update(http_status=http_status, extraction_status="error", exclusion_reason=reason)
    try:
        record["canonical_url"] = canonicalize_url(requested_url)
        record["record_id"] = record_id(record["canonical_url"])
    except ValueError:
        pass
    return record


def save_versioned_html(
    html: str,
    *,
    raw_html_root: str | Path,
    source_dataset: str,
    article_record_id: str,
    retrieved_at: str,
) -> Path:
    """Conserva cada descarga como una nueva versión sin sobrescribir HTML."""

    safe_source = re.sub(r"[^a-zA-Z0-9_.-]+", "_", source_dataset)
    safe_id = re.sub(r"[^a-zA-Z0-9_.-]+", "_", article_record_id or "unknown")
    stamp = re.sub(r"[^0-9A-Za-z]+", "", retrieved_at.replace("+00:00", "Z"))
    destination_dir = Path(raw_html_root) / safe_source
    destination_dir.mkdir(parents=True, exist_ok=True)
    candidate = destination_dir / f"{safe_id}_{stamp}.html"
    version = 2
    while candidate.exists():
        candidate = destination_dir / f"{safe_id}_{stamp}_v{version}.html"
        version += 1
    candidate.write_text(html, encoding="utf-8")
    return candidate
