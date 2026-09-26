#!/usr/bin/env python3
"""Consolida capturas locales en un CSV trazable listo para revisión humana."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

from dateutil import parser as date_parser
from peruvian_medical_misinformation.collection import find_exact_duplicates


FIELDS = [
    "record_id",
    "source_dataset",
    "source_id",
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
    "normalized_content_hash",
    "normalized_text",
    "extraction_status",
    "exclusion_reason",
    "duplicate_of",
    "period_status",
    "training_eligibility",
    "source_type",
    "discovery_method",
    "topic",
    "manifest_candidate_status",
    "manifest_notes",
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="data/interim/scraped_news.jsonl")
    parser.add_argument("--output", default="data/processed/medical_news_corpus_2026.csv")
    parser.add_argument("--start-date", default="2026-01-01")
    parser.add_argument("--end-date", default="2026-09-26")
    return parser.parse_args()


def _published_date(value: str) -> date | None:
    if not value.strip():
        return None
    try:
        return date_parser.parse(value, fuzzy=True).date()
    except (OverflowError, TypeError, ValueError):
        return None


def _text(record: dict[str, Any], key: str) -> str:
    return str(record.get(key, "") or "").strip()


def _row(record: dict[str, Any], *, start: date, end: date) -> dict[str, str]:
    body = _text(record, "body") or _text(record, "text")
    extraction_status = _text(record, "extraction_status")
    exclusion_reason = _text(record, "exclusion_reason")
    published_at = _text(record, "published_at")
    published = _published_date(published_at)
    period_status = "accepted"

    if published is None:
        period_status = "needs_date_review"
    elif not start <= published <= end:
        period_status = "outside_configured_period"
        extraction_status = "excluded_out_of_period"
        exclusion_reason = "Fecha de publicación fuera del periodo configurado"

    eligible = extraction_status == "ok" and period_status == "accepted" and bool(body)
    row = {field: "" for field in FIELDS}
    for field in FIELDS:
        if field in record:
            row[field] = _text(record, field)
    row.update(
        {
            "body": body,
            "extraction_status": extraction_status,
            "exclusion_reason": exclusion_reason,
            "period_status": period_status,
            "training_eligibility": "requires_human_review" if eligible else "not_trainable",
            "review_status": "pending" if eligible else "not_eligible",
        }
    )
    return row


def main() -> int:
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    try:
        start = date.fromisoformat(args.start_date)
        end = date.fromisoformat(args.end_date)
    except ValueError as error:
        raise SystemExit(f"Fecha de periodo inválida: {error}") from error
    if end < start:
        raise SystemExit("--end-date debe ser igual o posterior a --start-date")

    rows: list[dict[str, str]] = []
    with input_path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                raise SystemExit(f"JSON inválido en línea {line_number}: {error}") from error
            if not isinstance(record, dict):
                raise SystemExit(f"Registro inválido en línea {line_number}: se esperaba objeto JSON")
            rows.append(_row(record, start=start, end=end))

    duplicates = find_exact_duplicates(rows)
    for row in rows:
        original_id = duplicates.get(row["record_id"])
        if original_id:
            row["duplicate_of"] = original_id
            row["extraction_status"] = "duplicate_exact"
            row["exclusion_reason"] = "Duplicado exacto del contenido extraído"
            row["training_eligibility"] = "not_trainable"
            row["review_status"] = "not_eligible"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    by_source = Counter(row["source_name"] for row in rows)
    by_status = Counter(row["extraction_status"] for row in rows)
    eligible = sum(row["training_eligibility"] == "requires_human_review" for row in rows)
    print(f"Corpus CSV escrito: {output_path} ({len(rows)} registros)")
    print(f"Periodo configurado: {start.isoformat()} a {end.isoformat()}")
    print(f"Por fuente: {dict(sorted(by_source.items()))}")
    print(f"Por estado: {dict(sorted(by_status.items()))}")
    print(f"Elegibles para revisión humana: {eligible}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
