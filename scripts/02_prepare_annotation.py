#!/usr/bin/env python3
"""Convierte la captura JSONL en una plantilla de anotación binaria."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


FIELDS = [
    "record_id",
    "source_dataset",
    "url",
    "canonical_url",
    "source_id",
    "source_name",
    "domain",
    "published_at",
    "retrieved_at",
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
    "main_medical_claim",
    "evidence_source",
    "label",
    "evidence_url",
    "evidence_identifier",
    "evidence_excerpt",
    "label_reason",
    "reviewer_1",
    "reviewer_2",
    "review_status",
    "disagreement",
    "reviewed_at",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="data/interim/scraped_news_enriched.jsonl")
    parser.add_argument("--output", default="data/annotations/annotation_template.csv")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    if output_path.exists() and not args.force:
        raise SystemExit(f"Ya existe {output_path}; usa --force solo si deseas reemplazarlo")

    records: list[dict[str, str]] = []
    with input_path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            record = json.loads(line)
            row = {field: str(record.get(field, "") or "") for field in FIELDS}
            row["body"] = row["body"] or str(record.get("text", "") or "")
            records.append(row)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(records)
    print(f"Plantilla escrita: {output_path} ({len(records)} registros)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
