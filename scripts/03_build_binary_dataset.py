#!/usr/bin/env python3
"""Prepara el dataset binario futuro desde etiquetas humanas 0/1.

La fase de adquisición no ejecuta este script. Los casos ``EXCLUIDA`` se
mantienen auditables en la plantilla HITL, pero no pasan al dataset binario.
"""

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
    "source_dataset",
    "source_name",
    "published_at",
    "retrieved_at",
    "claim_text",
    "evidence_url",
    "evidence_type",
    "pmid",
    "pubmed_query",
    "query_date",
    "verdict_reason",
    "annotator_1",
    "annotator_2",
    "adjudication",
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
            label = (row.get("label") or "").strip()
            if not label or label == "EXCLUIDA":
                excluded += 1
                continue
            if label not in ALLOWED_LABELS:
                raise SystemExit(
                    f"Etiqueta no permitida para {row.get('record_id', '')}: {label}. "
                    "El dataset binario solo acepta 0 o 1; EXCLUIDA queda fuera."
                )
            record_id = (row.get("record_id") or "").strip()
            body = row.get("body") or row.get("text", "")
            text = "\n\n".join(
                part.strip()
                for part in (row.get("title", ""), row.get("subtitle_or_bajada", ""), body)
                if part.strip()
            )
            if not record_id or not text:
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
