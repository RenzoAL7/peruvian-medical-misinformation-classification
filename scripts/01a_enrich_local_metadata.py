#!/usr/bin/env python3
"""Completa metadatos desde HTML ya guardado, sin hacer solicitudes web."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

from peruvian_medical_misinformation.collection import extract_metadata, normalize_text


METADATA_FIELDS = ["title", "published_at", "subtitle_or_bajada", "author", "section"]
LOG_FIELDS = [
    "record_id",
    "source_dataset",
    "source_id",
    "source_name",
    "url",
    "canonical_url",
    "retrieved_at",
    "published_at",
    "http_status",
    "content_status",
    "extraction_status",
    "exclusion_reason",
    "scraping_method",
    "raw_html_path",
    "content_hash",
    "normalized_content_hash",
    "attempts",
    "error",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="data/interim/scraped_news.jsonl")
    parser.add_argument("--output", default="data/interim/scraped_news_enriched.jsonl")
    parser.add_argument(
        "--log",
        default="",
        help="log CSV limpio, una fila por URL procesada (opcional)",
    )
    return parser.parse_args()


def _text(record: dict[str, Any], key: str) -> str:
    return str(record.get(key, "") or "").strip()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    records: list[dict[str, Any]] = []
    updated = Counter()
    unavailable_html = 0

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

            raw_html_path = Path(_text(record, "raw_html_path"))
            if not raw_html_path.is_file():
                unavailable_html += 1
                records.append(record)
                continue
            metadata = extract_metadata(raw_html_path.read_text(encoding="utf-8"))
            for field in METADATA_FIELDS:
                if not _text(record, field) and metadata[field]:
                    record[field] = metadata[field]
                    updated[field] += 1
            record["normalized_text"] = normalize_text(
                _text(record, "title"),
                _text(record, "subtitle_or_bajada"),
                _text(record, "body") or _text(record, "text"),
            )
            records.append(record)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    if args.log:
        log_path = Path(args.log)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=LOG_FIELDS, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(records)

    print(f"JSONL enriquecido: {output_path} ({len(records)} registros)")
    print(f"Campos completados: {dict(sorted(updated.items()))}")
    print(f"Registros sin HTML local disponible: {unavailable_html}")
    if args.log:
        print(f"Log CSV limpio: {args.log}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
