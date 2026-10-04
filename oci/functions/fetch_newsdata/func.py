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
import time
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

# One country is processed per invocation.  Puerto Rico is included as a
# separate territory so its coverage is visible in the audit trail.
DEFAULT_COUNTRY_SEQUENCE = (
    "ar",
    "bo",
    "cl",
    "co",
    "cr",
    "cu",
    "do",
    "ec",
    "es",
    "gt",
    "gq",
    "hn",
    "mx",
    "ni",
    "pa",
    "pe",
    "pr",
    "py",
    "sv",
    "uy",
    "ve",
)


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


def _country_sequence() -> list[str]:
    """Return the ordered country cycle used by automatic collection."""

    configured = os.getenv("NEWSDATA_COUNTRY_SEQUENCE", "").strip()
    values = configured.split(",") if configured else list(DEFAULT_COUNTRY_SEQUENCE)
    sequence = [value.strip().lower() for value in values if value.strip()]
    if not sequence:
        raise RuntimeError("NEWSDATA_COUNTRY_SEQUENCE cannot be empty")
    if any(len(value) != 2 for value in sequence):
        raise RuntimeError("NEWSDATA_COUNTRY_SEQUENCE must contain ISO-2 country codes")
    return sequence


def _object_storage_client() -> Any:
    signer = oci.auth.signers.get_resource_principals_signer()
    return oci.object_storage.ObjectStorageClient(config={}, signer=signer)


def _state_object_name(prefix: str) -> str:
    return f"{prefix}/newsdata_coverage_state.json" if prefix else "newsdata_coverage_state.json"


def _load_coverage_state(
    client: Any,
    namespace: str,
    bucket: str,
    prefix: str,
) -> dict[str, Any]:
    """Load the country cursor; a missing state starts the first cycle."""

    try:
        object_response = client.get_object(
            namespace_name=namespace,
            bucket_name=bucket,
            object_name=_state_object_name(prefix),
        )
    except oci.exceptions.ServiceError as exc:
        if exc.status == 404:
            return {}
        raise

    content = object_response.data.content
    if hasattr(content, "read"):
        content = content.read()
    try:
        state = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("The country coverage state is not valid JSON") from exc
    if not isinstance(state, dict):
        raise RuntimeError("The country coverage state must be a JSON object")
    return state


def _coverage_cursor(
    client: Any,
    namespace: str,
    bucket: str,
    prefix: str,
) -> dict[str, Any] | None:
    """Select the next country unless an explicit country override is set."""

    explicit_country = os.getenv("NEWSDATA_COUNTRY", "").strip().lower()
    if explicit_country:
        return None

    sequence = _country_sequence()
    state = _load_coverage_state(client, namespace, bucket, prefix)
    stored_sequence = state.get("country_sequence")
    if stored_sequence != sequence:
        state = {"country_sequence": sequence, "next_index": 0, "cycle": 1}

    try:
        next_index = int(state.get("next_index", 0))
        cycle = int(state.get("cycle", 1))
    except (TypeError, ValueError) as exc:
        raise RuntimeError("The country coverage cursor is invalid") from exc
    if not 0 <= next_index < len(sequence):
        next_index = 0
    if cycle < 1:
        cycle = 1

    return {
        "country_sequence": sequence,
        "country_index": next_index,
        "cycle": cycle,
        "country": sequence[next_index],
    }


def _save_coverage_state(
    client: Any,
    namespace: str,
    bucket: str,
    prefix: str,
    state: dict[str, Any],
) -> None:
    encoded = json.dumps(state, ensure_ascii=False, indent=2).encode("utf-8")
    client.put_object(
        namespace_name=namespace,
        bucket_name=bucket,
        object_name=_state_object_name(prefix),
        put_object_body=io.BytesIO(encoded),
        content_type="application/json; charset=utf-8",
    )


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


def _existing_record_ids(
    client: Any,
    namespace: str,
    bucket: str,
    prefix: str,
) -> set[str]:
    """Read prior Bronze CSVs so a later 48-hour run cannot repeat records."""

    record_ids: set[str] = set()
    list_prefix = f"{prefix}/" if prefix else ""
    start: str | None = None

    while True:
        response = client.list_objects(
            namespace_name=namespace,
            bucket_name=bucket,
            prefix=list_prefix,
            start=start,
            fields="name",
            limit=1000,
        )
        for item in response.data.objects:
            object_name = str(item.name)
            if not object_name.endswith(".csv"):
                continue
            object_response = client.get_object(
                namespace_name=namespace,
                bucket_name=bucket,
                object_name=object_name,
            )
            content = object_response.data.content
            if hasattr(content, "read"):
                content = content.read()
            reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
            for row in reader:
                record_id = str(row.get("record_id") or "").strip()
                if record_id:
                    record_ids.add(record_id)

        start = response.data.next_start_with
        if not start:
            break
    return record_ids


def _request_newsdata(
    api_key: str,
    requested_country: str | None = None,
) -> tuple[dict[str, Any], dict[str, str]]:
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
    country = (
        requested_country.strip().lower()
        if requested_country is not None
        else os.getenv("NEWSDATA_COUNTRY", "").strip().lower()
    )
    if query:
        params["q"] = query
    if country:
        params["country"] = country

    try:
        max_pages = int(os.getenv("NEWSDATA_MAX_PAGES", "1"))
    except ValueError as exc:
        raise RuntimeError("NEWSDATA_MAX_PAGES must be an integer") from exc
    if not 1 <= max_pages <= 100:
        raise RuntimeError("NEWSDATA_MAX_PAGES must be between 1 and 100")

    try:
        timeout = float(os.getenv("NEWSDATA_TIMEOUT", "30"))
    except ValueError as exc:
        raise RuntimeError("NEWSDATA_TIMEOUT must be a number") from exc
    try:
        page_delay = float(os.getenv("NEWSDATA_PAGE_DELAY", "2"))
        max_retries = int(os.getenv("NEWSDATA_MAX_RETRIES", "3"))
    except ValueError as exc:
        raise RuntimeError("NEWSDATA_PAGE_DELAY and NEWSDATA_MAX_RETRIES must be numeric") from exc
    if page_delay < 0 or max_retries < 0:
        raise RuntimeError("NEWSDATA_PAGE_DELAY and NEWSDATA_MAX_RETRIES cannot be negative")

    all_results: list[Any] = []
    first_payload: dict[str, Any] | None = None
    next_page: str | None = None
    pages_fetched = 0
    last_status = ""

    while pages_fetched < max_pages:
        if pages_fetched and page_delay:
            time.sleep(page_delay)
        page_params = dict(params)
        if next_page:
            page_params["page"] = next_page
        request = Request(
            f"{endpoint}?{urlencode(page_params)}",
            headers={"Accept": "application/json", "User-Agent": "mednews-oci/0.1"},
            method="GET",
        )
        for attempt in range(max_retries + 1):
            try:
                with urlopen(request, timeout=timeout) as result:
                    raw = result.read()
                    last_status = str(result.status)
                break
            except HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                if exc.code != 429 or attempt >= max_retries:
                    raise RuntimeError(f"NewsData returned HTTP {exc.code}: {body[:500]}") from exc
                retry_after = exc.headers.get("Retry-After", "")
                try:
                    retry_delay = max(float(retry_after), 2.0 ** (attempt + 1))
                except ValueError:
                    retry_delay = 2.0 ** (attempt + 1)
                LOGGER.warning(
                    "NewsData rate limit on page %s; retrying in %.1f seconds",
                    pages_fetched + 1,
                    retry_delay,
                )
                time.sleep(retry_delay)
            except URLError as exc:
                raise RuntimeError(f"NewsData request failed: {exc.reason}") from exc

        try:
            page_payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError("NewsData returned a non-JSON response") from exc
        if not isinstance(page_payload, dict):
            raise RuntimeError("NewsData returned an unexpected JSON shape")
        if first_payload is None:
            first_payload = page_payload

        page_results = page_payload.get("results") or []
        if isinstance(page_results, list):
            all_results.extend(page_results)
        pages_fetched += 1
        next_page_value = page_payload.get("nextPage")
        next_page = str(next_page_value).strip() if next_page_value else None
        if not next_page:
            break

    payload = dict(first_payload or {})
    payload["results"] = all_results
    safe_params = {key: value for key, value in params.items() if key != "apikey"}
    safe_params.update(
        {
            "endpoint": endpoint,
            "requested_country": country,
            "http_status": last_status,
            "max_pages": str(max_pages),
            "pages_fetched": str(pages_fetched),
            "articles_received": str(len(all_results)),
            "next_page_available": str(bool(next_page)).lower(),
            "page_delay_seconds": str(page_delay),
            "max_retries": str(max_retries),
        }
    )
    return payload, safe_params


def _write_bronze(
    payload: dict[str, Any],
    request_meta: dict[str, str],
    requested_country: str,
    client: Any,
) -> dict[str, str]:
    namespace = _required_env("OBJECT_STORAGE_NAMESPACE")
    bucket = _required_env("OBJECT_STORAGE_BUCKET")
    prefix = os.getenv("BRONZE_PREFIX", "bronze").strip("/")
    retrieved_at = datetime.now(timezone.utc)
    run_id = f"run_{retrieved_at.strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
    country_label = requested_country or "global"
    object_name = f"{prefix}/newsdata_{country_label}_{run_id}.csv"
    rows = _bronze_rows(payload, retrieved_at.isoformat())

    dedup_enabled = os.getenv("BRONZE_DEDUP_ENABLED", "1").strip().lower() not in {
        "0",
        "false",
        "no",
    }
    existing_record_ids = (
        _existing_record_ids(client, namespace, bucket, prefix) if dedup_enabled else set()
    )
    original_row_count = len(rows)
    rows = [row for row in rows if row["record_id"] not in existing_record_ids]

    csv_buffer = io.StringIO(newline="")
    writer = csv.DictWriter(csv_buffer, fieldnames=BRONZE_FIELDS, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    encoded = csv_buffer.getvalue().encode("utf-8-sig")

    client.put_object(
        namespace_name=namespace,
        bucket_name=bucket,
        object_name=object_name,
        put_object_body=io.BytesIO(encoded),
        content_type="text/csv; charset=utf-8",
    )
    return {
        "run_id": run_id,
        "requested_country": requested_country,
        "bucket": bucket,
        "object_name": object_name,
        "row_count": str(len(rows)),
        "candidate_row_count": str(original_row_count),
        "duplicates_skipped": str(original_row_count - len(rows)),
        "existing_record_ids": str(len(existing_record_ids)),
        "dedup_enabled": str(dedup_enabled).lower(),
        "request_total_results": str(payload.get("totalResults") or 0),
        "request_meta": json.dumps(request_meta, ensure_ascii=False),
    }


def handler(ctx: Any, data: io.BytesIO | None = None) -> response.Response:
    """Fetch one country and write its deduplicated Bronze CSV."""

    try:
        secret_id = _required_env("NEWSDATA_SECRET_OCID")
        api_key = _secret_value(secret_id)
        if not api_key:
            raise RuntimeError("The NewsData secret is empty")
        namespace = _required_env("OBJECT_STORAGE_NAMESPACE")
        bucket = _required_env("OBJECT_STORAGE_BUCKET")
        prefix = os.getenv("BRONZE_PREFIX", "bronze").strip("/")
        client = _object_storage_client()
        cursor = _coverage_cursor(client, namespace, bucket, prefix)
        requested_country = (
            cursor["country"] if cursor is not None else os.getenv("NEWSDATA_COUNTRY", "").strip().lower()
        )
        payload, request_meta = _request_newsdata(api_key, requested_country=requested_country)
        result = _write_bronze(payload, request_meta, requested_country, client)

        if cursor is not None:
            sequence = cursor["country_sequence"]
            next_index = cursor["country_index"] + 1
            next_cycle = cursor["cycle"]
            if next_index >= len(sequence):
                next_index = 0
                next_cycle += 1
            next_state = {
                "country_sequence": sequence,
                "next_index": next_index,
                "next_country": sequence[next_index],
                "cycle": next_cycle,
                "last_country": requested_country,
                "last_run_id": result["run_id"],
                "last_row_count": int(result["row_count"]),
                "last_duplicates_skipped": int(result["duplicates_skipped"]),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            _save_coverage_state(client, namespace, bucket, prefix, next_state)
            result.update(
                {
                    "coverage_cycle": str(cursor["cycle"]),
                    "country_index": str(cursor["country_index"]),
                    "next_country": next_state["next_country"],
                }
            )
        else:
            result["coverage_mode"] = "explicit_country"
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
