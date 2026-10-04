"""OCI Function that stores NewsData candidates in the Bronze layer.

The function deliberately keeps collection separate from later article-body
extraction and labeling. It reads the NewsData token from OCI Vault using a
resource principal and writes one Excel-compatible CSV per run to Object
Storage.
"""

from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

import oci
from fdk import response


LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)


BRONZE_FIELDS = [
    "record_id",
    "source_name",
    "canonical_url",
    "published_at",
    "title",
    "subtitle_or_bajada",
    "topic",
    "selection_status",
    "retrieved_at",
    "country",
]

TRACKING_PARAMETERS = {"fbclid", "gclid", "mc_cid", "mc_eid"}


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _secret_value(secret_id: str) -> str:
    signer = oci.auth.signers.get_resource_principals_signer()
    client = oci.secrets.SecretsClient(config={}, signer=signer)
    bundle = client.get_secret_bundle(secret_id=secret_id, stage="CURRENT").data
    content = bundle.secret_bundle_content.content
    return base64.b64decode(content).decode("utf-8").strip()


def _canonicalize_url(raw_url: str) -> str:
    """Remove tracking parameters so the same article gets one record_id."""

    parsed = urlsplit(raw_url.strip())
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ValueError("invalid article URL")
    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in TRACKING_PARAMETERS and not key.lower().startswith("utm_")
    ]
    hostname = parsed.hostname.lower()
    netloc = hostname if parsed.port is None else f"{hostname}:{parsed.port}"
    return urlunsplit((parsed.scheme.lower(), netloc, parsed.path or "/", urlencode(query), ""))


def _record_id(canonical_url: str) -> str:
    return hashlib.sha256(canonical_url.encode("utf-8")).hexdigest()[:16]


def _list_value(value: Any) -> str:
    if isinstance(value, list):
        return ",".join(str(item).strip() for item in value if str(item).strip())
    return str(value or "").strip()


def _bronze_rows(payload: dict[str, Any], retrieved_at: str) -> list[dict[str, str]]:
    """Map API articles to the ten columns used by the thesis Bronze sheet."""

    rows: list[dict[str, str]] = []
    seen_record_ids: set[str] = set()
    results = payload.get("results") or []
    if not isinstance(results, list):
        return rows

    for item in results:
        if not isinstance(item, dict):
            continue
        language = str(item.get("language") or "").strip().casefold()
        if language not in {"es", "spanish"}:
            continue
        category_text = _list_value(item.get("category")).casefold()
        categories = {value.strip() for value in category_text.split(",") if value.strip()}
        if "health" not in categories:
            continue

        raw_url = str(item.get("link") or "").strip()
        if not raw_url:
            continue
        try:
            canonical_url = _canonicalize_url(raw_url)
        except ValueError:
            continue
        record_id = _record_id(canonical_url)
        if record_id in seen_record_ids:
            continue
        seen_record_ids.add(record_id)

        rows.append(
            {
                "record_id": record_id,
                "source_name": str(item.get("source_name") or "").strip(),
                "canonical_url": canonical_url,
                "published_at": str(item.get("pubDate") or item.get("pub_date") or "").strip(),
                "title": str(item.get("title") or "").strip(),
                "subtitle_or_bajada": str(item.get("description") or "").strip(),
                "topic": "health",
                "selection_status": "PENDIENTE",
                "retrieved_at": retrieved_at,
                "country": _list_value(item.get("country")),
            }
        )
    return rows


def _request_newsdata(api_key: str) -> tuple[dict[str, Any], dict[str, str]]:
    endpoint = os.getenv("NEWSDATA_ENDPOINT", "https://newsdata.io/api/1/latest").strip()
    params: dict[str, str] = {
        "apikey": api_key,
        "language": os.getenv("NEWSDATA_LANGUAGE", "es").strip(),
        "category": os.getenv("NEWSDATA_CATEGORY", "health").strip(),
        "size": os.getenv("NEWSDATA_SIZE", "10").strip(),
        "removeduplicate": os.getenv("NEWSDATA_REMOVEDUPLICATE", "1").strip(),
        "video": os.getenv("NEWSDATA_VIDEO", "0").strip(),
    }
    query = os.getenv(
        "NEWSDATA_QUERY",
        "(cáncer OR diabetes OR vacuna OR medicamento OR tratamiento)",
    ).strip()
    country = os.getenv("NEWSDATA_COUNTRY", "").strip()
    if query:
        params["q"] = query
    if country:
        params["country"] = country

    request = Request(
        f"{endpoint}?{urlencode(params)}",
        headers={"Accept": "application/json", "User-Agent": "mednews-oci/0.1"},
        method="GET",
    )
    try:
        with urlopen(request, timeout=float(os.getenv("NEWSDATA_TIMEOUT", "30"))) as result:
            raw = result.read()
            status = str(result.status)
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"NewsData returned HTTP {exc.code}: {body[:500]}") from exc
    except URLError as exc:
        raise RuntimeError(f"NewsData request failed: {exc.reason}") from exc

    try:
        payload = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError("NewsData returned a non-JSON response") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("NewsData returned an unexpected JSON shape")

    safe_params = {key: value for key, value in params.items() if key != "apikey"}
    safe_params["endpoint"] = endpoint
    safe_params["http_status"] = status
    return payload, safe_params


def _write_bronze(payload: dict[str, Any], request_meta: dict[str, str]) -> dict[str, str]:
    namespace = _required_env("OBJECT_STORAGE_NAMESPACE")
    bucket = _required_env("OBJECT_STORAGE_BUCKET")
    prefix = os.getenv("BRONZE_PREFIX", "bronze").strip("/")
    retrieved_at = datetime.now(timezone.utc)
    run_id = f"run_{retrieved_at.strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
    object_name = f"{prefix}/newsdata_{run_id}.csv"
    rows = _bronze_rows(payload, retrieved_at.isoformat())
    csv_buffer = io.StringIO(newline="")
    writer = csv.DictWriter(csv_buffer, fieldnames=BRONZE_FIELDS, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    encoded = csv_buffer.getvalue().encode("utf-8-sig")

    signer = oci.auth.signers.get_resource_principals_signer()
    client = oci.object_storage.ObjectStorageClient(config={}, signer=signer)
    client.put_object(
        namespace_name=namespace,
        bucket_name=bucket,
        object_name=object_name,
        put_object_body=io.BytesIO(encoded),
        content_type="text/csv; charset=utf-8",
    )
    return {
        "run_id": run_id,
        "bucket": bucket,
        "object_name": object_name,
        "row_count": str(len(rows)),
        "request_total_results": str(payload.get("totalResults") or 0),
        "request_meta": json.dumps(request_meta, ensure_ascii=False),
    }


def handler(ctx: Any, data: io.BytesIO | None = None) -> response.Response:
    """Fetch NewsData and write the Bronze CSV."""

    try:
        secret_id = _required_env("NEWSDATA_SECRET_OCID")
        api_key = _secret_value(secret_id)
        if not api_key:
            raise RuntimeError("The NewsData secret is empty")
        payload, request_meta = _request_newsdata(api_key)
        result = _write_bronze(payload, request_meta)
        LOGGER.info("Bronze CSV written: %s (%s rows)", result["object_name"], result["row_count"])
        return response.Response(
            ctx,
            response_data=json.dumps({"status": "ok", **result}),
            headers={"Content-Type": "application/json"},
        )
    except Exception as exc:  # noqa: BLE001 - the invocation must return a useful error
        LOGGER.exception("fetch-newsdata failed")
        return response.Response(
            ctx,
            response_data=json.dumps({"status": "error", "message": str(exc)}),
            status_code=500,
            headers={"Content-Type": "application/json"},
        )
