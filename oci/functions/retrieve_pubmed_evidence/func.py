"""Retrieve PubMed evidence candidates for English query-enriched claims.

The function is deliberately an evidence-retrieval step. It does not decide
whether a news claim is true or false. It reads up to a small batch of claim
rows, queries PubMed with ESearch, downloads all returned records in one
EFetch request, ranks the abstracts with a transparent local TF-IDF cosine
score, and writes one output row per claim. The top-k PubMed candidates are
stored as JSON inside that row so the CSV does not expand to one row per paper.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import math
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timezone
from typing import Any

import oci
from fdk import response


LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)

PUBMED_BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
COSINE_METHOD = "tfidf_v1"

OUTPUT_FIELDS = [
    "record_id",
    "country",
    "source_name",
    "canonical_url",
    "published_at",
    "title",
    "claim_text",
    "claim_text_en",
    "claim_type",
    "pubmed_query_en",
    "evidence_status",
    "evidence_error",
    "pubmed_result_count",
    "best_pmid",
    "best_cosine_similarity",
    "pubmed_results_json",
    "source_claims_object",
    "claim_run_id",
    "evidence_run_id",
    "cosine_method",
    "retrieved_at",
]


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _env_int(name: str, default: int, minimum: int | None = None, maximum: int | None = None) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if minimum is not None and value < minimum:
        raise RuntimeError(f"{name} must be at least {minimum}")
    if maximum is not None and value > maximum:
        raise RuntimeError(f"{name} must be at most {maximum}")
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


def _row_complete(row: dict[str, str]) -> bool:
    return (
        row.get("query_status", "").strip().upper() == "OK"
        and bool(row.get("claim_text_en", "").strip())
        and bool(row.get("pubmed_query_en", "").strip())
    )


def _row_priority(row: dict[str, str]) -> tuple[int, str]:
    timestamp = row.get("query_enriched_at", "") or row.get("llm_processed_at", "")
    return (1 if _row_complete(row) else 0, timestamp)


def _latest_claim_rows(
    client: Any,
    namespace: str,
    bucket: str,
    claims_prefix: str,
) -> tuple[dict[str, dict[str, str]], dict[str, int]]:
    rows_by_id: dict[str, dict[str, str]] = {}
    objects = _list_csv_objects(client, namespace, bucket, claims_prefix)
    rows_seen = 0
    for object_name in objects:
        for source_row in _read_csv_object(client, namespace, bucket, object_name):
            rows_seen += 1
            record_id = source_row.get("record_id", "").strip()
            if not record_id:
                continue
            row = dict(source_row)
            row["source_claims_object"] = object_name
            previous = rows_by_id.get(record_id)
            if previous is None or _row_priority(row) >= _row_priority(previous):
                rows_by_id[record_id] = row
    return rows_by_id, {
        "claims_objects_scanned": len(objects),
        "claims_rows_seen": rows_seen,
        "unique_claims": len(rows_by_id),
    }


def _existing_evidence_ids(
    client: Any,
    namespace: str,
    bucket: str,
    evidence_prefix: str,
) -> set[str]:
    record_ids: set[str] = set()
    for object_name in _list_csv_objects(client, namespace, bucket, evidence_prefix):
        for row in _read_csv_object(client, namespace, bucket, object_name):
            record_id = row.get("record_id", "").strip()
            if record_id:
                record_ids.add(record_id)
    return record_ids


def _select_claims(
    rows_by_id: dict[str, dict[str, str]],
    completed_evidence_ids: set[str],
    batch_size: int,
) -> tuple[list[dict[str, str]], dict[str, int]]:
    selected: list[dict[str, str]] = []
    stats = Counter(
        {
            "claims_seen": len(rows_by_id),
            "skipped_existing_evidence": 0,
            "skipped_not_eligible": 0,
            "skipped_missing_query": 0,
        }
    )
    for record_id in sorted(rows_by_id):
        row = rows_by_id[record_id]
        if record_id in completed_evidence_ids:
            stats["skipped_existing_evidence"] += 1
            continue
        eligible = row.get("is_claim_eligible", "").strip().lower() == "true"
        if not eligible or not row.get("claim_text", "").strip():
            stats["skipped_not_eligible"] += 1
            continue
        if not _row_complete(row):
            stats["skipped_missing_query"] += 1
            continue
        selected.append(row)
        if len(selected) >= batch_size:
            break
    stats["selected"] = len(selected)
    return selected, dict(stats)


def _http_request(
    endpoint: str,
    params: dict[str, str],
    timeout: float,
    accept: str,
) -> bytes:
    query = urllib.parse.urlencode(params, doseq=True)
    request = urllib.request.Request(
        f"{endpoint}?{query}",
        headers={"Accept": accept, "User-Agent": "mednews-thesis/0.1"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as result:
            return result.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1200]
        raise RuntimeError(f"PubMed HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"PubMed network error: {exc.reason}") from exc


def _search_pubmed(
    query: str,
    top_k: int,
    tool: str,
    email: str,
    api_key: str,
    timeout: float,
) -> list[str]:
    params = {
        "db": "pubmed",
        "term": query,
        "retmode": "json",
        "retmax": str(top_k),
        "sort": "relevance",
        "tool": tool,
        "email": email,
    }
    if api_key:
        params["api_key"] = api_key
    payload = json.loads(
        _http_request(
            f"{PUBMED_BASE_URL}/esearch.fcgi",
            params,
            timeout,
            "application/json",
        ).decode("utf-8", errors="replace")
    )
    return [str(value) for value in payload.get("esearchresult", {}).get("idlist", [])]


def _element_text(element: ET.Element | None) -> str:
    if element is None:
        return ""
    return re.sub(r"\s+", " ", "".join(element.itertext())).strip()


def _fetch_pubmed(
    pmids: list[str],
    tool: str,
    email: str,
    api_key: str,
    timeout: float,
) -> dict[str, dict[str, Any]]:
    if not pmids:
        return {}
    params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "xml",
        "rettype": "abstract",
        "tool": tool,
        "email": email,
    }
    if api_key:
        params["api_key"] = api_key
    root = ET.fromstring(
        _http_request(
            f"{PUBMED_BASE_URL}/efetch.fcgi",
            params,
            timeout,
            "application/xml",
        )
    )
    records: dict[str, dict[str, Any]] = {}
    for article in root.findall(".//PubmedArticle"):
        pmid = _element_text(article.find(".//PMID"))
        if not pmid:
            continue
        title = _element_text(article.find(".//ArticleTitle"))
        abstract_parts = [
            _element_text(node)
            for node in article.findall(".//Abstract/AbstractText")
            if _element_text(node)
        ]
        abstract = " ".join(abstract_parts)
        journal = _element_text(article.find(".//Journal/Title"))
        pub_date = _element_text(article.find(".//ArticleDate")) or _element_text(
            article.find(".//PubDate")
        )
        doi = ""
        for article_id in article.findall(".//ArticleId"):
            if str(article_id.attrib.get("IdType", "")).lower() == "doi":
                doi = _element_text(article_id)
                break
        publication_types = [
            _element_text(node)
            for node in article.findall(".//PublicationType")
            if _element_text(node)
        ]
        records[pmid] = {
            "pmid": pmid,
            "title": title,
            "abstract": abstract,
            "journal": journal,
            "publication_date": pub_date,
            "doi": doi,
            "publication_types": publication_types,
        }
    return records


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)?", text.lower())


def _cosine_similarity(left: str, right: str) -> float:
    left_tokens = _tokens(left)
    right_tokens = _tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    left_counts = Counter(left_tokens)
    right_counts = Counter(right_tokens)
    vocabulary = set(left_counts) | set(right_counts)
    document_frequency = {
        token: int(token in left_counts) + int(token in right_counts)
        for token in vocabulary
    }
    left_vector: dict[str, float] = {}
    right_vector: dict[str, float] = {}
    total_left = len(left_tokens)
    total_right = len(right_tokens)
    for token in vocabulary:
        idf = math.log((1.0 + 2.0) / (1.0 + document_frequency[token])) + 1.0
        left_vector[token] = (left_counts[token] / total_left) * idf
        right_vector[token] = (right_counts[token] / total_right) * idf
    numerator = sum(left_vector[token] * right_vector[token] for token in vocabulary)
    left_norm = math.sqrt(sum(value * value for value in left_vector.values()))
    right_norm = math.sqrt(sum(value * value for value in right_vector.values()))
    if not left_norm or not right_norm:
        return 0.0
    return numerator / (left_norm * right_norm)


def _candidate_results(
    row: dict[str, str],
    pmids: list[str],
    records: dict[str, dict[str, Any]],
    top_k: int,
    abstract_max_chars: int,
) -> list[dict[str, Any]]:
    claim_en = row.get("claim_text_en", "")
    candidates: list[dict[str, Any]] = []
    for pubmed_rank, pmid in enumerate(pmids, start=1):
        article = records.get(pmid)
        if not article:
            continue
        comparison_text = f"{article.get('title', '')} {article.get('abstract', '')}".strip()
        score = _cosine_similarity(claim_en, comparison_text)
        candidates.append(
            {
                "pmid": pmid,
                "title": article.get("title", ""),
                "abstract_excerpt": article.get("abstract", "")[:abstract_max_chars],
                "journal": article.get("journal", ""),
                "publication_date": article.get("publication_date", ""),
                "doi": article.get("doi", ""),
                "publication_types": article.get("publication_types", []),
                "pubmed_url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                "pubmed_rank": pubmed_rank,
                "cosine_similarity": round(score, 4),
            }
        )
    candidates.sort(key=lambda item: (-float(item["cosine_similarity"]), int(item["pubmed_rank"])))
    return candidates[:top_k]


def _base_output_row(row: dict[str, str], run_id: str, retrieved_at: str) -> dict[str, str]:
    return {
        "record_id": row.get("record_id", ""),
        "country": row.get("country", ""),
        "source_name": row.get("source_name", ""),
        "canonical_url": row.get("canonical_url", ""),
        "published_at": row.get("published_at", ""),
        "title": row.get("title", ""),
        "claim_text": row.get("claim_text", ""),
        "claim_text_en": row.get("claim_text_en", ""),
        "claim_type": row.get("claim_type", ""),
        "pubmed_query_en": row.get("pubmed_query_en", ""),
        "evidence_status": "",
        "evidence_error": "",
        "pubmed_result_count": "0",
        "best_pmid": "",
        "best_cosine_similarity": "",
        "pubmed_results_json": "[]",
        "source_claims_object": row.get("source_claims_object", ""),
        "claim_run_id": row.get("claim_run_id", ""),
        "evidence_run_id": run_id,
        "cosine_method": COSINE_METHOD,
        "retrieved_at": retrieved_at,
    }


def _write_evidence(
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
    object_name = f"{prefix.strip('/')}/evidence_batch_{run_id}.csv"
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
    retrieved_at = now.isoformat()
    try:
        namespace = _required_env("OBJECT_STORAGE_NAMESPACE")
        bucket = _required_env("OBJECT_STORAGE_BUCKET")
        claims_prefix = os.getenv("SILVER_CLAIMS_PREFIX", "silver/claims").strip("/")
        evidence_prefix = os.getenv("SILVER_EVIDENCE_PREFIX", "silver/evidence").strip("/")
        batch_size = _env_int("EVIDENCE_BATCH_SIZE", 10, minimum=1, maximum=50)
        top_k = _env_int("PUBMED_TOP_K", 5, minimum=1, maximum=20)
        request_delay = _env_float("PUBMED_REQUEST_DELAY", 0.4, minimum=0.34)
        request_timeout = _env_float("PUBMED_REQUEST_TIMEOUT", 20.0, minimum=5.0)
        max_seconds = _env_float("EVIDENCE_MAX_SECONDS", 240.0, minimum=5.0)
        abstract_max_chars = _env_int("ABSTRACT_MAX_CHARS", 3000, minimum=500, maximum=10000)
        tool = os.getenv("PUBMED_TOOL", "mednews-thesis").strip() or "mednews-thesis"
        email = _required_env("PUBMED_EMAIL")
        api_key = os.getenv("PUBMED_API_KEY", "").strip()
        deadline = started + max_seconds - 10.0

        storage = _object_storage_client()
        claim_rows, scan_meta = _latest_claim_rows(storage, namespace, bucket, claims_prefix)
        existing_ids = _existing_evidence_ids(storage, namespace, bucket, evidence_prefix)
        pending, selection_meta = _select_claims(claim_rows, existing_ids, batch_size)

        query_pmids: dict[str, list[str]] = {}
        errors: dict[str, str] = {}
        pubmed_requests = 0
        for row in pending:
            if time.monotonic() >= deadline:
                errors[row.get("record_id", "")] = "EVIDENCE_TIME_BUDGET"
                continue
            try:
                query_pmids[row["record_id"]] = _search_pubmed(
                    row["pubmed_query_en"][:1000],
                    top_k,
                    tool,
                    email,
                    api_key,
                    request_timeout,
                )
                pubmed_requests += 1
            except Exception as exc:  # noqa: BLE001 - keep other claims moving
                errors[row.get("record_id", "")] = f"{type(exc).__name__}: {exc}"[:1500]
            remaining = deadline - time.monotonic()
            if remaining > request_delay:
                time.sleep(request_delay)

        all_pmids: list[str] = []
        for pmids in query_pmids.values():
            for pmid in pmids:
                if pmid not in all_pmids:
                    all_pmids.append(pmid)

        records: dict[str, dict[str, Any]] = {}
        if all_pmids and time.monotonic() < deadline:
            try:
                records = _fetch_pubmed(all_pmids, tool, email, api_key, request_timeout)
                pubmed_requests += 1
            except Exception as exc:  # noqa: BLE001 - preserve claim-level error output
                fetch_error = f"{type(exc).__name__}: {exc}"[:1500]
                for row in pending:
                    if row.get("record_id") in query_pmids:
                        errors[row.get("record_id", "")] = fetch_error

        output_rows: list[dict[str, str]] = []
        status_counts: Counter[str] = Counter()
        for row in pending:
            record_id = row.get("record_id", "")
            output = _base_output_row(row, run_id, retrieved_at)
            if record_id in errors:
                output["evidence_status"] = "ERROR"
                output["evidence_error"] = errors[record_id]
            else:
                pmids = query_pmids.get(record_id, [])
                candidates = _candidate_results(row, pmids, records, top_k, abstract_max_chars)
                output["pubmed_result_count"] = str(len(candidates))
                output["pubmed_results_json"] = json.dumps(candidates, ensure_ascii=False)
                if not pmids:
                    output["evidence_status"] = "NO_RESULTS"
                elif not candidates:
                    output["evidence_status"] = "NO_ABSTRACT"
                else:
                    output["evidence_status"] = "OK"
                    output["best_pmid"] = str(candidates[0].get("pmid", ""))
                    output["best_cosine_similarity"] = str(candidates[0].get("cosine_similarity", ""))
            status_counts[output["evidence_status"]] += 1
            output_rows.append(output)

        object_name = ""
        if output_rows:
            object_name = _write_evidence(
                storage,
                namespace,
                bucket,
                evidence_prefix,
                output_rows,
                run_id,
            )

        result = {
            "status": "ok" if not status_counts.get("ERROR") else "partial",
            "run_id": run_id,
            "bucket": bucket,
            "object_name": object_name,
            "row_count": str(len(output_rows)),
            "status_counts": dict(status_counts),
            "rows_left_for_next_run": str(max(0, len(claim_rows) - len(existing_ids) - len(output_rows))),
            "pubmed_requests": str(pubmed_requests),
            "top_k": str(top_k),
            "batch_size": str(batch_size),
            "cosine_method": COSINE_METHOD,
            "elapsed_seconds": f"{time.monotonic() - started:.2f}",
            "scan": scan_meta,
            "selection": selection_meta,
        }
        LOGGER.info("Silver evidence batch written: %s (%s rows)", object_name or "none", len(output_rows))
        return response.Response(
            ctx,
            response_data=json.dumps(result, ensure_ascii=False),
            headers={"Content-Type": "application/json"},
        )
    except Exception as exc:  # noqa: BLE001 - expose useful invocation errors
        LOGGER.exception("retrieve-pubmed-evidence failed")
        return response.Response(
            ctx,
            response_data=json.dumps({"status": "error", "run_id": run_id, "message": str(exc)}),
            status_code=500,
            headers={"Content-Type": "application/json"},
        )
