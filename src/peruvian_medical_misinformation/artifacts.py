"""Lectura, escritura y resumen de artefactos reproducibles del corpus."""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from .corpus import CORPUS_FIELDS
from .deduplication import mark_duplicates


ANNOTATION_FIELDS = [
    *CORPUS_FIELDS,
    "main_medical_claim",
    "evidence_source",
    "evidence_url",
    "evidence_identifier",
    "evidence_excerpt",
    "label",
    "label_reason",
    "reviewer_1",
    "reviewer_2",
    "review_status",
    "disagreement",
    "reviewed_at",
]

LOG_FIELDS = [
    "run_id",
    "record_id",
    "source_dataset",
    "source_name",
    "url",
    "canonical_url",
    "http_status",
    "retrieved_at",
    "published_at",
    "extraction_status",
    "exclusion_reason",
    "duplicate_status",
    "raw_html_path",
]

SUMMARY_MISSINGNESS_FIELDS = [
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
    "raw_html_path",
    "content_hash",
    "normalized_text",
    "normalized_content_hash",
]


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    source = Path(path)
    if not source.exists():
        return records
    with source.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"JSONL inválido en {source}:{line_number}") from error
            if not isinstance(value, dict):
                raise ValueError(f"Registro no objeto en {source}:{line_number}")
            records.append(value)
    return records


def write_jsonl(path: str | Path, records: Iterable[dict[str, Any]], *, append: bool = False) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    with destination.open(mode, encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def append_log(path: str | Path, records: Iterable[dict[str, Any]]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    write_header = not destination.exists() or destination.stat().st_size == 0
    with destination.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=LOG_FIELDS, extrasaction="ignore")
        if write_header:
            writer.writeheader()
        for record in records:
            writer.writerow({field: record.get(field, "") for field in LOG_FIELDS})


def write_extraction_log(path: str | Path, records: Iterable[dict[str, Any]]) -> None:
    """Escribe el log consolidado con estados de extracción y duplicación finales."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=LOG_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for record in records:
            writer.writerow({field: record.get(field, "") for field in LOG_FIELDS})


def normalize_columns(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{field: record.get(field, "") for field in CORPUS_FIELDS} for record in records]


def consolidate_records(
    records: Iterable[dict[str, Any]],
    *,
    near_duplicate_threshold: float,
) -> list[dict[str, Any]]:
    return mark_duplicates(normalize_columns(records), near_duplicate_threshold)


def write_corpus(
    records: Iterable[dict[str, Any]],
    *,
    csv_path: str | Path,
    parquet_path: str | Path,
) -> None:
    table = pd.DataFrame(list(records), columns=CORPUS_FIELDS)
    csv_destination = Path(csv_path)
    parquet_destination = Path(parquet_path)
    csv_destination.parent.mkdir(parents=True, exist_ok=True)
    parquet_destination.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(csv_destination, index=False, encoding="utf-8")
    table.to_parquet(parquet_destination, index=False, engine="pyarrow")


def annotation_rows(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in records:
        if record.get("extraction_status") != "valid" or record.get("duplicate_status") != "unique":
            continue
        row = {field: record.get(field, "") for field in ANNOTATION_FIELDS}
        row.update(
            main_medical_claim="",
            evidence_source="",
            evidence_url="",
            evidence_identifier="",
            evidence_excerpt="",
            label="",
            label_reason="",
            reviewer_1="",
            reviewer_2="",
            review_status="pendiente",
            disagreement="",
            reviewed_at="",
        )
        rows.append(row)
    return rows


def write_annotation_template(path: str | Path, rows: Iterable[dict[str, Any]]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=ANNOTATION_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def collection_summary(records: Iterable[dict[str, Any]], *, minimum_records: int) -> dict[str, Any]:
    rows = list(records)
    by_source = Counter(str(row.get("source_dataset") or "sin_fuente") for row in rows)
    by_status = Counter(str(row.get("extraction_status") or "sin_estado") for row in rows)
    by_duplicate = Counter(str(row.get("duplicate_status") or "sin_estado") for row in rows)
    valid_unique = sum(
        row.get("extraction_status") == "valid" and row.get("duplicate_status") == "unique" for row in rows
    )
    valid_unique_by_source = Counter(
        str(row.get("source_dataset") or "sin_fuente")
        for row in rows
        if row.get("extraction_status") == "valid" and row.get("duplicate_status") == "unique"
    )
    missing_field_counts = {
        field: sum(not str(row.get(field) or "").strip() for row in rows)
        for field in SUMMARY_MISSINGNESS_FIELDS
    }
    original_label_counts: dict[str, dict[str, int]] = {}
    for source_dataset in sorted(by_source):
        labels = Counter(
            str(row.get("source_original_label") or "").strip()
            for row in rows
            if str(row.get("source_dataset") or "sin_fuente") == source_dataset
            and str(row.get("source_original_label") or "").strip()
        )
        if labels:
            original_label_counts[source_dataset] = dict(sorted(labels.items()))
    return {
        "records_total": len(rows),
        "records_valid_unique": valid_unique,
        "minimum_records_before_annotation": minimum_records,
        "minimum_reached": valid_unique >= minimum_records,
        "records_missing_to_minimum": max(0, minimum_records - valid_unique),
        "by_source_dataset": dict(sorted(by_source.items())),
        "valid_unique_by_source_dataset": dict(sorted(valid_unique_by_source.items())),
        "by_extraction_status": dict(sorted(by_status.items())),
        "by_duplicate_status": dict(sorted(by_duplicate.items())),
        "errors": sum(row.get("extraction_status") == "error" for row in rows),
        "excluded": sum(row.get("extraction_status") == "excluded" for row in rows),
        "missing_field_counts": missing_field_counts,
        "source_original_label_counts": original_label_counts,
        "label_semantics_status": "unmapped_pending_human_evidence_review",
    }


def write_summary(path: str | Path, summary: dict[str, Any]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
