#!/usr/bin/env python3
"""Construye el dataset final aceptando únicamente las etiquetas 0 y 1."""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path


OUTPUT_FIELDS = [
    "record_id",
    "text",
    "label",
    "url",
    "canonical_url",
    "source_id",
    "source_name",
    "published_at",
    "retrieved_at",
    "main_medical_claim",
    "label_reason",
    "evidence_url",
    "evidence_source",
    "evidence_identifier",
    "reviewer_1",
    "reviewer_2",
    "reviewed_at",
]
ALLOWED_LABELS = {"0", "1"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="data/annotations/annotation_template.csv")
    parser.add_argument("--output", default="data/processed/medical_misinformation_binary.csv")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    if output_path.exists() and not args.force:
        raise SystemExit(f"Ya existe {output_path}; usa --force solo si deseas reemplazarlo")

    rows: list[dict[str, str]] = []
    seen: dict[str, str] = {}
    excluded = 0
    with input_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        required = {"record_id", "title", "label"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise SystemExit(f"Faltan columnas obligatorias: {sorted(missing)}")
        for row in reader:
            label = (row.get("label") or "").strip().upper()
            if not label:
                excluded += 1
                continue
            if label not in ALLOWED_LABELS:
                raise SystemExit(
                    f"Etiqueta no permitida para {row.get('record_id', '')}: {label}. "
                    "El dataset solo acepta 0 o 1."
                )
            record_id = (row.get("record_id") or "").strip()
            body = (row.get("body") or row.get("text") or "").strip()
            text = "\n\n".join(
                part.strip()
                for part in (
                    row.get("title", ""),
                    row.get("subtitle_or_bajada", ""),
                    body,
                )
                if part.strip()
            )
            if (row.get("training_eligibility") or "").strip() not in {
                "",
                "requires_human_review",
            }:
                excluded += 1
                continue
            if not record_id or not body or not text:
                excluded += 1
                continue
            previous_label = seen.get(record_id)
            if previous_label and previous_label != label:
                raise SystemExit(f"Conflicto de etiqueta para record_id={record_id}")
            if previous_label:
                excluded += 1
                continue
            seen[record_id] = label
            rows.append(
                {
                    "record_id": record_id,
                    "text": text,
                    "label": label,
                    **{field: (row.get(field) or "").strip() for field in OUTPUT_FIELDS if field not in {"record_id", "text", "label"}},
                }
            )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    counts = Counter(row["label"] for row in rows)
    print(f"Dataset binario escrito: {output_path}")
    print(f"Registros incluidos: {len(rows)}; excluidos por estar incompletos o sin etiqueta: {excluded}")
    print(f"Distribución: {dict(counts)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
