"""Funciones seguras y reproducibles para extracción dirigida de artículos."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
from bs4 import BeautifulSoup

try:
    import trafilatura
except ImportError:  # pragma: no cover - exercised when the optional extra is absent
    trafilatura = None


TRACKING_PARAMETERS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
}


def canonicalize_url(url: str) -> str:
    """Normaliza una URL y elimina fragmentos y parámetros de seguimiento."""

    parsed = urlsplit(url.strip())
    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError("La URL debe usar HTTP o HTTPS")
    if not parsed.hostname:
        raise ValueError("La URL no contiene un dominio")

    hostname = parsed.hostname.lower()
    netloc = hostname
    if parsed.port is not None:
        netloc = f"{hostname}:{parsed.port}"

    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in TRACKING_PARAMETERS
        and not key.lower().startswith("utm_")
    ]
    path = parsed.path or "/"
    return urlunsplit((parsed.scheme.lower(), netloc, path, urlencode(query), ""))


def is_allowed_domain(url: str, allowed_domains: list[str]) -> bool:
    """Comprueba una coincidencia exacta o un subdominio autorizado."""

    hostname = (urlsplit(url).hostname or "").lower().rstrip(".")
    normalized_domains = [domain.lower().lstrip(".").rstrip(".") for domain in allowed_domains]
    return any(hostname == domain or hostname.endswith(f".{domain}") for domain in normalized_domains)


def record_id(canonical_url: str) -> str:
    """Devuelve un identificador estable y no reversible para una URL."""

    return hashlib.sha256(canonical_url.encode("utf-8")).hexdigest()[:16]


def _meta_content(soup: BeautifulSoup, *names: str) -> str:
    for name in names:
        tag = soup.find("meta", attrs={"property": name}) or soup.find(
            "meta", attrs={"name": name}
        )
        if tag and tag.get("content"):
            return str(tag["content"]).strip()
    return ""


def _jsonld_date(soup: BeautifulSoup) -> str:
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            value = json.loads(script.string or script.get_text())
        except (TypeError, json.JSONDecodeError):
            continue
        candidates = value if isinstance(value, list) else [value]
        for candidate in candidates:
            if isinstance(candidate, Mapping):
                for key in ("datePublished", "dateCreated"):
                    if candidate.get(key):
                        return str(candidate[key]).strip()
    return ""


def extract_metadata(html: str) -> dict[str, str]:
    """Extrae título y fecha sin asumir una plantilla concreta del medio."""

    soup = BeautifulSoup(html, "html.parser")
    title = _meta_content(soup, "og:title", "twitter:title")
    if not title and soup.title:
        title = soup.title.get_text(" ", strip=True)

    published_at = _meta_content(
        soup,
        "article:published_time",
        "datePublished",
        "pubdate",
        "date",
    )
    if not published_at:
        published_at = _jsonld_date(soup)
    return {"title": title, "published_at": published_at}


def extract_text(html: str) -> tuple[str, str]:
    """Extrae texto y devuelve también el método utilizado."""

    if trafilatura is not None:
        extracted = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=False,
            include_links=False,
        )
        if extracted and len(extracted.strip()) >= 80:
            return re.sub(r"\n{3,}", "\n\n", extracted).strip(), "trafilatura"

    soup = BeautifulSoup(html, "html.parser")
    for element in soup(["script", "style", "noscript", "nav", "footer", "header", "form"]):
        element.decompose()
    paragraphs = []
    for paragraph in soup.find_all("p"):
        text = re.sub(r"\s+", " ", paragraph.get_text(" ", strip=True)).strip()
        if len(text) >= 40:
            paragraphs.append(text)
    return "\n\n".join(paragraphs).strip(), "beautifulsoup_fallback"


def collect_url(
    client: httpx.Client,
    *,
    url: str,
    source_id: str,
    source_name: str,
    allowed_domains: list[str],
) -> dict[str, Any]:
    """Descarga una URL permitida y devuelve un registro serializable."""

    retrieved_at = datetime.now(timezone.utc).isoformat()
    base: dict[str, Any] = {
        "record_id": "",
        "url": url.strip(),
        "canonical_url": "",
        "source_id": source_id,
        "source_name": source_name,
        "domain": "",
        "retrieved_at": retrieved_at,
        "published_at": "",
        "title": "",
        "text": "",
        "content_hash": "",
        "extraction_method": "",
        "content_status": "pending",
        "http_status": None,
        "error": "",
    }

    try:
        canonical_url = canonicalize_url(url)
        if not is_allowed_domain(canonical_url, allowed_domains):
            raise ValueError("El dominio no está permitido para esta fuente")
    except ValueError as error:
        base["content_status"] = "rejected"
        base["error"] = str(error)
        return base

    base["canonical_url"] = canonical_url
    base["record_id"] = record_id(canonical_url)
    base["domain"] = urlsplit(canonical_url).hostname or ""

    try:
        response = client.get(canonical_url)
        base["http_status"] = response.status_code
        response.raise_for_status()
    except httpx.HTTPError as error:
        base["content_status"] = "http_error"
        base["error"] = f"{type(error).__name__}: {error}"
        return base

    try:
        final_url = canonicalize_url(str(response.url))
    except (AttributeError, ValueError) as error:
        base["content_status"] = "redirect_not_allowed"
        base["error"] = f"URL final inválida: {error}"
        return base
    if not is_allowed_domain(final_url, allowed_domains):
        base["content_status"] = "redirect_not_allowed"
        base["error"] = "La redirección terminó fuera del dominio permitido"
        return base
    base["canonical_url"] = final_url
    base["record_id"] = record_id(final_url)
    base["domain"] = urlsplit(final_url).hostname or ""

    content_type = response.headers.get("content-type", "").lower()
    if content_type and "html" not in content_type:
        base["content_status"] = "not_html"
        base["error"] = f"Content-Type no HTML: {content_type}"
        return base

    metadata = extract_metadata(response.text)
    text, method = extract_text(response.text)
    base.update(
        {
            "published_at": metadata["published_at"],
            "title": metadata["title"],
            "text": text,
            "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest()
            if text
            else "",
            "extraction_method": method,
            "content_status": "ok" if len(text) >= 200 else "needs_review",
        }
    )
    if not text:
        base["error"] = "No se pudo extraer texto suficiente"
    return base
