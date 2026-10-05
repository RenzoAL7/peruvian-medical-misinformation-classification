"""Extract auditable medical claims from valid Silver article bodies.

This Function is deliberately a candidate-generation step.  It does not decide
whether a claim is true or false.  Rows whose body extraction failed, is too
short, or is missing are excluded before the OCI Generative AI call.  Valid
rows are sent one at a time to ``google.gemini-2.5-flash`` and the structured
response is written to a new CSV under ``silver/claims/``.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import os
import re
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from typing import Any

import oci
from fdk import response


LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)

PROMPT_VERSION = "claim-extraction-v1"
DEFAULT_MODEL_ID = "google.gemini-2.5-flash"
CLAIM_TYPES = {"tratamiento", "prevención", "diagnóstico", "riesgo", "causa", "síntoma", "otro"}

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

BODY_FIELDS = [
    "body",
    "http_status",
    "extraction_method",
    "extraction_status",
    "body_char_count",
    "body_word_count",
    "extracted_at",
    "source_bronze_object",
    "extraction_run_id",
    "extraction_error",
]

CLAIM_FIELDS = [
    "claim_text",
    "is_medical",
    "is_claim_eligible",
    "claim_type",
    "llm_reason",
    "needs_human_review",
    "llm_status",
    "llm_error",
    "llm_raw_json",
    "model_id",
    "prompt_version",
    "llm_processed_at",
    "source_silver_object",
    "claim_run_id",
]

OUTPUT_FIELDS = BRONZE_FIELDS + BODY_FIELDS + CLAIM_FIELDS


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _env_int(name: str, default: int, minimum: int | None = None) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if minimum is not None and value < minimum:
        raise RuntimeError(f"{name} must be at least {minimum}")
    return value


def _env_float(name: str, default: float, minimum: float | None = None) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a number") from exc
    if minimum is not None and value < minimum:
        raise RuntimeError(f"{name} must be at least {minimum}")
    return value


def _object_storage_client() -> Any:
    signer = oci.auth.signers.get_resource_principals_signer()
    return oci.object_storage.ObjectStorageClient(config={}, signer=signer)


def _generative_ai_client(region: str, request_timeout: float) -> Any:
    signer = oci.auth.signers.get_resource_principals_signer()
    endpoint = os.getenv(
        "GENAI_ENDPOINT",
        f"https://inference.generativeai.{region}.oci.oraclecloud.com",
    ).strip()
    return oci.generative_ai_inference.GenerativeAiInferenceClient(
        config={"region": region},
        signer=signer,
        service_endpoint=endpoint,
        timeout=(5.0, request_timeout),
        retry_strategy=oci.retry.NoneRetryStrategy(),
    )


def _list_csv_objects(client: Any, namespace: str, bucket: str, prefix: str) -> list[str]:
    list_prefix = f"{prefix.strip('/')}/" if prefix.strip("/") else ""
    names: list[str] = []
    start: str | None = None
    while True:
        result = client.list_objects(
            namespace_name=namespace,
            bucket_name=bucket,
            prefix=list_prefix,
            start=start,
            fields="name",
            limit=1000,
        )
        for item in result.data.objects:
            name = str(item.name)
            if name.endswith(".csv"):
                names.append(name)
        start = result.data.next_start_with
        if not start:
            break
    return sorted(set(names))


def _read_csv_object(client: Any, namespace: str, bucket: str, object_name: str) -> list[dict[str, str]]:
    result = client.get_object(
        namespace_name=namespace,
        bucket_name=bucket,
        object_name=object_name,
    )
    content = result.data.content
    if hasattr(content, "read"):
        content = content.read()
    if not isinstance(content, (bytes, bytearray)):
        raise RuntimeError(f"Object Storage returned non-byte content for {object_name}")
    reader = csv.DictReader(io.StringIO(bytes(content).decode("utf-8-sig", errors="replace")))
    return [
        {str(key): str(value or "").strip() for key, value in row.items() if key}
        for row in reader
        if row
    ]


def _existing_claim_ids(client: Any, namespace: str, bucket: str, prefix: str) -> set[str]:
    record_ids: set[str] = set()
    for object_name in _list_csv_objects(client, namespace, bucket, prefix):
        for row in _read_csv_object(client, namespace, bucket, object_name):
            record_id = row.get("record_id", "").strip()
            if record_id:
                record_ids.add(record_id)
    return record_ids


def _pending_rows(
    client: Any,
    namespace: str,
    bucket: str,
    body_prefix: str,
    claims_prefix: str,
    batch_size: int,
) -> tuple[list[dict[str, str]], dict[str, int]]:
    """Select valid, not-yet-attempted bodies across all Silver CSVs."""

    attempted_ids = _existing_claim_ids(client, namespace, bucket, claims_prefix)
    selected_ids: set[str] = set()
    selected: list[dict[str, str]] = []
    stats = Counter(
        {
            "body_objects_scanned": 0,
            "body_rows_seen": 0,
            "skipped_no_body": 0,
            "skipped_extraction_error": 0,
            "skipped_duplicate": 0,
            "claims_record_ids": len(attempted_ids),
        }
    )
    body_objects = _list_csv_objects(client, namespace, bucket, body_prefix)
    stats["body_objects_scanned"] = len(body_objects)

    for object_name in body_objects:
        for source_row in _read_csv_object(client, namespace, bucket, object_name):
            stats["body_rows_seen"] += 1
            record_id = source_row.get("record_id", "").strip()
            body = source_row.get("body", "").strip()
            extraction_status = source_row.get("extraction_status", "").strip().upper()
            if not record_id or not body:
                stats["skipped_no_body"] += 1
                continue
            if extraction_status != "OK":
                stats["skipped_extraction_error"] += 1
                continue
            if record_id in attempted_ids or record_id in selected_ids:
                stats["skipped_duplicate"] += 1
                continue
            selected_ids.add(record_id)
            selected.append(
                {
                    field: source_row.get(field, "").strip()
                    for field in BRONZE_FIELDS + BODY_FIELDS
                }
                | {"source_silver_object": object_name}
            )
            if len(selected) >= batch_size:
                return selected, dict(stats)

    return selected, dict(stats)


def _build_prompt(row: dict[str, str], max_body_chars: int) -> str:
    body = row.get("body", "")[:max_body_chars]
    title = row.get("title", "")
    subtitle = row.get("subtitle_or_bajada", "")
    return f"""Eres un extractor de afirmaciones médicas para un corpus académico en español.

Devuelve únicamente un objeto JSON válido con exactamente estas claves:
{{
  "is_medical": true,
  "is_claim_eligible": true,
  "claim_text": "una sola afirmación médica concreta",
  "claim_type": "tratamiento|prevención|diagnóstico|riesgo|causa|síntoma|otro",
  "reason": "explicación breve basada en el texto",
  "needs_human_review": true
}}

Reglas:
- Extrae la afirmación principal, sin inventar datos ni completar información ausente.
- No decidas si la afirmación es verdadera o falsa; esa decisión requiere evidencia y revisión humana.
- is_medical es false si el texto no trata sobre salud, enfermedad, medicina o bienestar.
- is_claim_eligible es false y claim_text debe ser "" si no existe una afirmación médica concreta que pueda verificarse.
- Mantén claim_text en español y en una sola oración.
- needs_human_review debe ser true para cualquier afirmación elegible.

Título: {title}
Subtítulo: {subtitle}
Texto del artículo:
<<<
{body}
>>>
"""


def _to_plain(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        try:
            return value.to_dict()
        except Exception:  # noqa: BLE001
            pass
    # OCI SDK model objects expose ``swagger_types`` and private backing
    # attributes rather than a public ``to_dict`` method in this base image.
    if hasattr(value, "swagger_types"):
        return {
            name: _to_plain(getattr(value, name, None))
            for name in value.swagger_types
        }
    if isinstance(value, dict):
        return {str(k): _to_plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_plain(v) for v in value]
    return value


def _find_response_text(value: Any) -> str:
    """Find assistant text across SDK response versions."""

    value = _to_plain(value)
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        for item in value:
            text = _find_response_text(item)
            if text:
                return text
        return ""
    if not isinstance(value, dict):
        return ""
    for key in ("text", "content", "chat_response", "choices", "message", "response", "data"):
        if key in value:
            text = _find_response_text(value[key])
            if text:
                return text
    return ""


def _json_payload(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start < 0 or end <= start:
            raise
        payload = json.loads(cleaned[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("LLM response is not a JSON object")
    return payload


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "sí", "si", "yes"}
    return default


def _normalize_claim(payload: dict[str, Any]) -> dict[str, str]:
    claim_type = str(payload.get("claim_type", "otro")).strip().lower()
    if claim_type not in CLAIM_TYPES:
        claim_type = "otro"
    claim_text = re.sub(r"\s+", " ", str(payload.get("claim_text", "") or "")).strip()
    reason = re.sub(r"\s+", " ", str(payload.get("reason", "") or "")).strip()
    is_medical = _as_bool(payload.get("is_medical"))
    eligible = _as_bool(payload.get("is_claim_eligible")) and bool(claim_text)
    if not is_medical or not eligible:
        claim_text = ""
        eligible = False
    return {
        "claim_text": claim_text[:2000],
        "is_medical": str(is_medical).lower(),
        "is_claim_eligible": str(eligible).lower(),
        "claim_type": claim_type,
        "llm_reason": reason[:2000],
        "needs_human_review": str(_as_bool(payload.get("needs_human_review"), default=eligible)).lower(),
    }


def _chat_request(model_id: str, prompt: str, max_tokens: int, temperature: float, top_p: float) -> Any:
    models = oci.generative_ai_inference.models
    return models.ChatDetails(
        compartment_id=_required_env("GENAI_COMPARTMENT_ID"),
        serving_mode=models.OnDemandServingMode(model_id=model_id),
        chat_request=models.GenericChatRequest(
            api_format="GENERIC",
            messages=[
                models.UserMessage(
                    role="USER",
                    content=[models.TextContent(type="TEXT", text=prompt)],
                )
            ],
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            response_format=models.JsonObjectResponseFormat(type="JSON_OBJECT"),
        ),
    )


def _call_llm(
    client: Any,
    row: dict[str, str],
    model_id: str,
    max_body_chars: int,
    max_tokens: int,
    temperature: float,
    top_p: float,
    retries: int,
    deadline: float,
) -> tuple[dict[str, str], str]:
    prompt = _build_prompt(row, max_body_chars)
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        if time.monotonic() >= deadline:
            raise TimeoutError("LLM batch time budget reached")
        try:
            result = client.chat(
                chat_details=_chat_request(model_id, prompt, max_tokens, temperature, top_p),
                retry_strategy=oci.retry.NoneRetryStrategy(),
            )
            raw_text = _find_response_text(result)
            if not raw_text:
                raise ValueError("OCI Generative AI returned an empty response")
            payload = _json_payload(raw_text)
            return _normalize_claim(payload), json.dumps(payload, ensure_ascii=False)
        except Exception as exc:  # noqa: BLE001 - retry transient service/parse errors once
            last_error = exc
            if attempt < retries and time.monotonic() + 1.0 < deadline:
                time.sleep(1.0)
    raise RuntimeError(f"LLM call failed: {type(last_error).__name__}: {last_error}") from last_error


def _output_row(
    source_row: dict[str, str],
    claim: dict[str, str],
    raw_json: str,
    run_id: str,
    model_id: str,
    status: str,
    error: str = "",
) -> dict[str, str]:
    output = {field: source_row.get(field, "") for field in BRONZE_FIELDS + BODY_FIELDS}
    output.update(claim)
    output.update(
        {
            "llm_status": status,
            "llm_error": error[:1000],
            "llm_raw_json": raw_json[:8000],
            "model_id": model_id,
            "prompt_version": PROMPT_VERSION,
            "llm_processed_at": datetime.now(timezone.utc).isoformat(),
            "source_silver_object": source_row.get("source_silver_object", ""),
            "claim_run_id": run_id,
        }
    )
    return output


def _quota_disabled(error: Exception) -> bool:
    message = str(error).lower()
    return "set to 0" in message or "tokens-per-minute" in message and "429" in message


def _write_claims(
    client: Any,
    namespace: str,
    bucket: str,
    prefix: str,
    rows: list[dict[str, str]],
    run_id: str,
) -> str:
    csv_buffer = io.StringIO(newline="")
    writer = csv.DictWriter(csv_buffer, fieldnames=OUTPUT_FIELDS, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    object_name = f"{prefix.strip('/')}/claims_batch_{run_id}.csv"
    client.put_object(
        namespace_name=namespace,
        bucket_name=bucket,
        object_name=object_name,
        put_object_body=io.BytesIO(csv_buffer.getvalue().encode("utf-8-sig")),
        content_type="text/csv; charset=utf-8",
    )
    return object_name


def handler(ctx: Any, data: io.BytesIO | None = None) -> response.Response:
    started = time.monotonic()
    now = datetime.now(timezone.utc)
    run_id = f"run_{now.strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
    try:
        namespace = _required_env("OBJECT_STORAGE_NAMESPACE")
        bucket = _required_env("OBJECT_STORAGE_BUCKET")
        body_prefix = os.getenv("SILVER_BODY_PREFIX", "silver/body").strip("/")
        claims_prefix = os.getenv("SILVER_CLAIMS_PREFIX", "silver/claims").strip("/")
        model_id = os.getenv("LLM_MODEL_ID", DEFAULT_MODEL_ID).strip() or DEFAULT_MODEL_ID
        region = os.getenv("LLM_REGION", os.getenv("OCI_REGION", "us-ashburn-1")).strip()
        batch_size = _env_int("LLM_BATCH_SIZE", 10, minimum=1)
        max_seconds = _env_float("LLM_MAX_SECONDS", 240.0, minimum=1.0)
        time_buffer = _env_float("LLM_TIME_BUFFER", 10.0, minimum=0.0)
        max_body_chars = _env_int("LLM_MAX_BODY_CHARS", 12_000, minimum=500)
        max_tokens = _env_int("LLM_MAX_TOKENS", 600, minimum=50)
        request_timeout = _env_float("LLM_REQUEST_TIMEOUT", 30.0, minimum=5.0)
        temperature = _env_float("LLM_TEMPERATURE", 0.1, minimum=0.0)
        top_p = _env_float("LLM_TOP_P", 0.9, minimum=0.0)
        retries = _env_int("LLM_MAX_RETRIES", 1, minimum=0)
        if time_buffer >= max_seconds:
            raise RuntimeError("LLM_TIME_BUFFER must be smaller than LLM_MAX_SECONDS")

        storage = _object_storage_client()
        pending, scan_meta = _pending_rows(
            storage,
            namespace,
            bucket,
            body_prefix,
            claims_prefix,
            batch_size,
        )
        deadline = started + max_seconds - time_buffer
        output_rows: list[dict[str, str]] = []
        statuses: Counter[str] = Counter()
        last_llm_error = ""
        consecutive_errors = 0
        if pending:
            llm = _generative_ai_client(region, request_timeout)
            for source_row in pending:
                if time.monotonic() >= deadline:
                    break
                try:
                    claim, raw_json = _call_llm(
                        llm,
                        source_row,
                        model_id,
                        max_body_chars,
                        max_tokens,
                        temperature,
                        top_p,
                        retries,
                        deadline,
                    )
                    output_rows.append(
                        _output_row(source_row, claim, raw_json, run_id, model_id, "OK")
                    )
                    statuses["OK"] += 1
                    consecutive_errors = 0
                except TimeoutError:
                    break
                except Exception as exc:  # noqa: BLE001 - keep failed rows pending for a later retry
                    LOGGER.warning("Claim extraction failed for %s: %s", source_row.get("record_id"), exc)
                    statuses["ERROR"] += 1
                    last_llm_error = f"{type(exc).__name__}: {exc}"[:2000]
                    consecutive_errors += 1
                    # A disabled tenancy quota cannot be fixed by sending the
                    # remaining rows; leave all of them pending and return
                    # immediately instead of spending more calls/time.
                    if _quota_disabled(exc) or consecutive_errors >= 3:
                        break

        object_name = ""
        if output_rows:
            object_name = _write_claims(storage, namespace, bucket, claims_prefix, output_rows, run_id)
        result_status = "ok"
        if statuses.get("ERROR", 0) and not output_rows:
            result_status = "error"
        elif statuses.get("ERROR", 0):
            result_status = "partial"
        result = {
            "status": result_status,
            "run_id": run_id,
            "bucket": bucket,
            "object_name": object_name,
            "row_count": str(len(output_rows)),
            "ok_rows": str(statuses.get("OK", 0)),
            "error_rows": str(statuses.get("ERROR", 0)),
            "rows_left_for_next_run": str(max(0, len(pending) - len(output_rows))),
            "llm_error": last_llm_error,
            "model_id": model_id,
            "elapsed_seconds": f"{time.monotonic() - started:.2f}",
            "batch_size": str(batch_size),
            "scan": scan_meta,
        }
        LOGGER.info("Silver claims batch written: %s (%s rows)", object_name or "none", len(output_rows))
        return response.Response(
            ctx,
            response_data=json.dumps(result, ensure_ascii=False),
            headers={"Content-Type": "application/json"},
        )
    except Exception as exc:  # noqa: BLE001 - expose a useful invocation error
        LOGGER.exception("extract-claims failed")
        return response.Response(
            ctx,
            response_data=json.dumps({"status": "error", "run_id": run_id, "message": str(exc)}),
            status_code=500,
            headers={"Content-Type": "application/json"},
        )
