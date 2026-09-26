"""Funciones seguras y reproducibles para extracción dirigida de artículos."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
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


def _iter_jsonld_mappings(value: Any):
    """Recorre objetos JSON-LD, incluidos los grafos anidados."""

    if isinstance(value, Mapping):
        yield value
        for nested in value.values():
            yield from _iter_jsonld_mappings(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _iter_jsonld_mappings(nested)


def _jsonld_value(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, Mapping):
        for key in ("name", "@id"):
            if isinstance(value.get(key), str) and value[key].strip():
                return value[key].strip()
    if isinstance(value, list):
        values = [_jsonld_value(item) for item in value]
        return "; ".join(value for value in values if value)
    return ""


def _jsonld_metadata(soup: BeautifulSoup) -> dict[str, str]:
    metadata = {
        "title": "",
        "published_at": "",
        "subtitle_or_bajada": "",
        "author": "",
        "section": "",
    }
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            value = json.loads(script.string or script.get_text())
        except (TypeError, json.JSONDecodeError):
            continue
        for candidate in _iter_jsonld_mappings(value):
            fields = {
                "title": ("headline", "name"),
                "published_at": ("datePublished", "dateCreated"),
                "subtitle_or_bajada": ("description",),
                "author": ("author",),
                "section": ("articleSection",),
            }
            for field, keys in fields.items():
                if metadata[field]:
                    continue
                for key in keys:
                    extracted = _jsonld_value(candidate.get(key))
                    if extracted:
                        metadata[field] = extracted
                        break
    return metadata


def extract_metadata(html: str) -> dict[str, str]:
    """Extrae los metadatos disponibles sin asumir una plantilla concreta."""

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
    jsonld_metadata = _jsonld_metadata(soup)
    return {
        "title": title or jsonld_metadata["title"],
        "published_at": published_at or jsonld_metadata["published_at"],
        "subtitle_or_bajada": _meta_content(
            soup, "og:description", "twitter:description", "description"
        )
        or jsonld_metadata["subtitle_or_bajada"],
        "author": _meta_content(soup, "article:author", "author")
        or jsonld_metadata["author"],
        "section": _meta_content(soup, "article:section", "section")
        or jsonld_metadata["section"],
    }


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


def normalize_text(*parts: str) -> str:
    """Normaliza Unicode y espacios, conservando tildes y negaciones."""

    text = "\n\n".join(part.strip() for part in parts if part and part.strip())
    text = unicodedata.normalize("NFKC", text)
    return re.sub(r"\s+", " ", text).strip()


def find_exact_duplicates(records: list[Mapping[str, Any]]) -> dict[str, str]:
    """Relaciona cada registro repetido con el primer contenido idéntico."""

    original_by_hash: dict[str, str] = {}
    duplicates: dict[str, str] = {}
    for record in records:
        record_id = str(record.get("record_id", "") or "")
        content_hash = str(record.get("content_hash", "") or "")
        body = str(record.get("body", "") or record.get("text", "") or "")
        if not record_id or not content_hash or not body:
            continue
        original_id = original_by_hash.get(content_hash)
        if original_id:
            duplicates[record_id] = original_id
        else:
            original_by_hash[content_hash] = record_id
    return duplicates


def _write_versioned_html(html: str, *, canonical_url: str, directory: Path) -> str:
    """Guarda HTML sin sobrescribir capturas anteriores de la misma URL."""

    directory.mkdir(parents=True, exist_ok=True)
    url_hash = hashlib.sha256(canonical_url.encode("utf-8")).hexdigest()[:16]
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = directory / f"{url_hash}-{timestamp}.html"
    counter = 1
    while path.exists():
        path = directory / f"{url_hash}-{timestamp}-{counter}.html"
        counter += 1
    path.write_text(html, encoding="utf-8")
    return str(path)


def collect_url(
    client: httpx.Client,
    *,
    url: str,
    source_id: str,
    source_name: str,
    allowed_domains: list[str],
    source_dataset: str | None = None,
    raw_html_dir: Path | None = None,
) -> dict[str, Any]:
    """Descarga una URL permitida y devuelve un registro serializable."""

    retrieved_at = datetime.now(timezone.utc).isoformat()
    base: dict[str, Any] = {
        "record_id": "",
        "url": url.strip(),
        "canonical_url": "",
        "source_id": source_id,
        "source_dataset": source_dataset or f"scraped_{source_id}",
        "source_name": source_name,
        "domain": "",
        "retrieved_at": retrieved_at,
        "published_at": "",
        "title": "",
        "subtitle_or_bajada": "",
        "body": "",
        "author": "",
        "section": "",
        "language": "es",
        "text": "",
        "normalized_text": "",
        "content_hash": "",
        "normalized_content_hash": "",
        "extraction_method": "",
        "scraping_method": "",
        "raw_html_path": "",
        "extraction_status": "pending",
        "exclusion_reason": "",
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
        base["extraction_status"] = "excluded"
        base["exclusion_reason"] = str(error)
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
        base["extraction_status"] = "error"
        base["exclusion_reason"] = "Error HTTP durante la solicitud"
        base["error"] = f"{type(error).__name__}: {error}"
        return base

    try:
        final_url = canonicalize_url(str(response.url))
    except (AttributeError, ValueError) as error:
        base["content_status"] = "redirect_not_allowed"
        base["extraction_status"] = "excluded"
        base["exclusion_reason"] = "Redirección final inválida"
        base["error"] = f"URL final inválida: {error}"
        return base
    if not is_allowed_domain(final_url, allowed_domains):
        base["content_status"] = "redirect_not_allowed"
        base["extraction_status"] = "excluded"
        base["exclusion_reason"] = "Redirección fuera del dominio permitido"
        base["error"] = "La redirección terminó fuera del dominio permitido"
        return base
    base["canonical_url"] = final_url
    base["record_id"] = record_id(final_url)
    base["domain"] = urlsplit(final_url).hostname or ""

    content_type = response.headers.get("content-type", "").lower()
    if content_type and "html" not in content_type:
        base["content_status"] = "not_html"
        base["extraction_status"] = "excluded"
        base["exclusion_reason"] = "La respuesta no es HTML"
        base["error"] = f"Content-Type no HTML: {content_type}"
        return base

    metadata = extract_metadata(response.text)
    text, method = extract_text(response.text)
    normalized_text = normalize_text(
        metadata["title"], metadata["subtitle_or_bajada"], text
    )
    status = "ok" if len(text) >= 200 else "needs_review"
    exclusion_reason = "" if status == "ok" else "Texto vacío o menor al umbral de 200 caracteres"
    raw_html_path = ""
    html_storage_error = ""
    if raw_html_dir is not None:
        try:
            raw_html_path = _write_versioned_html(
                response.text, canonical_url=final_url, directory=raw_html_dir
            )
        except OSError as error:
            html_storage_error = f"{type(error).__name__}: {error}"
    base.update(
        {
            "published_at": metadata["published_at"],
            "title": metadata["title"],
            "subtitle_or_bajada": metadata["subtitle_or_bajada"],
            "body": text,
            "author": metadata["author"],
            "section": metadata["section"],
            "text": text,
            "normalized_text": normalized_text,
            "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest() if text else "",
            "normalized_content_hash": (
                hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()
                if normalized_text
                else ""
            ),
            "raw_html_path": raw_html_path,
            "extraction_method": method,
            "scraping_method": method,
            "content_status": status,
            "extraction_status": status,
            "exclusion_reason": exclusion_reason,
        }
    )
    if html_storage_error:
        base["content_status"] = "storage_error"
        base["extraction_status"] = "error"
        base["exclusion_reason"] = "No se pudo guardar el HTML original"
        base["error"] = html_storage_error
    if not text:
        base["error"] = "No se pudo extraer texto suficiente"
    return base
