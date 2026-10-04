"""OCI Function that stores a NewsData response in the Bronze layer.

The function deliberately keeps collection separate from later article-body
extraction and labeling. It reads the NewsData token from OCI Vault using a
resource principal and writes an auditable JSON object to Object Storage.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import oci
from fdk import response


LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)


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


def _request_newsdata(api_key: str) -> tuple[dict[str, Any], dict[str, str]]:
    endpoint = os.getenv("NEWSDATA_ENDPOINT", "https://newsdata.io/api/1/latest").strip()
    params: dict[str, str] = {
        "apikey": api_key,
        "language": os.getenv("NEWSDATA_LANGUAGE", "es").strip(),
        "category": os.getenv("NEWSDATA_CATEGORY", "health").strip(),
    }
    query = os.getenv("NEWSDATA_QUERY", "").strip()
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
    prefix = os.getenv("BRONZE_PREFIX", "bronze/newsdata").strip("/")
    retrieved_at = datetime.now(timezone.utc)
    run_id = f"run_{retrieved_at.strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
    object_name = f"{prefix}/{retrieved_at.strftime('%Y/%m/%d')}/{run_id}.json"
    document = {
        "run_id": run_id,
        "retrieved_at": retrieved_at.isoformat(),
        "source": "newsdata",
        "request": request_meta,
        "response": payload,
    }
    encoded = json.dumps(document, ensure_ascii=False, indent=2).encode("utf-8")

    signer = oci.auth.signers.get_resource_principals_signer()
    client = oci.object_storage.ObjectStorageClient(config={}, signer=signer)
    client.put_object(
        namespace_name=namespace,
        bucket_name=bucket,
        object_name=object_name,
        put_object_body=io.BytesIO(encoded),
        content_type="application/json",
    )
    return {"run_id": run_id, "bucket": bucket, "object_name": object_name}


def handler(ctx: Any, data: io.BytesIO | None = None) -> response.Response:
    """Fetch NewsData and write the raw response to Bronze."""

    try:
        secret_id = _required_env("NEWSDATA_SECRET_OCID")
        api_key = _secret_value(secret_id)
        if not api_key:
            raise RuntimeError("The NewsData secret is empty")
        payload, request_meta = _request_newsdata(api_key)
        result = _write_bronze(payload, request_meta)
        LOGGER.info("Bronze object written: %s", result["object_name"])
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
