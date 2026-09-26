#!/usr/bin/env python3
"""Importa la base de noticias de Salud de Edwin sin convertir sus etiquetas."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from peruvian_medical_misinformation.artifacts import write_jsonl
from peruvian_medical_misinformation.importers import import_edwin_health_rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="XLSX original; nunca se modifica.")
    parser.add_argument("--sheet", default="DATASET ULIMA 1189")
    parser.add_argument("--output", default="data/raw/metadata/edwin_157.jsonl")
    parser.add_argument("--run-id", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = Path(args.input)
    if not source.exists():
        raise SystemExit(f"No existe el archivo original: {source}")
    run_id = args.run_id or f"edwin_import_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    records = import_edwin_health_rows(source, sheet_name=args.sheet, run_id=run_id)
    write_jsonl(args.output, records)
    labels = Counter(record.get("source_original_label", "") for record in records)
    print(f"Registros Salud importados: {len(records)}")
    print(f"Etiquetas originales preservadas, sin mapear: {dict(sorted(labels.items()))}")
    print(f"Metadatos escritos: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
