#!/usr/bin/env python3
"""Convierte la captura JSONL en una plantilla de anotación binaria."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


FIELDS = [
    "record_id",
    "url",
    "canonical_url",
    "source_id",
    "source_name",
    "domain",
    "published_at",
    "retrieved_at",
    "title",
    "text",
    "content_status",
    "claim_text",
    "label",
    "evidence_url",
    "evidence_type",
    "pmid",
    "pubmed_query",
    "query_date",
    "verdict_reason",
    "annotator_1",
    "annotator_2",
    "adjudication",
    "notes",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="data/raw/articles.jsonl")
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
    seen: set[str] = set()
    with input_path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            record = json.loads(line)
            record_id = str(record.get("record_id", ""))
            canonical_url = str(record.get("canonical_url", ""))
            dedup_key = record_id or canonical_url
            if not dedup_key or dedup_key in seen:
                continue
            seen.add(dedup_key)
            row = {field: str(record.get(field, "") or "") for field in FIELDS}
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
