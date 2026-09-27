#!/usr/bin/env python3
"""Crea una plantilla CSV para revisión manual de candidatas de NewsData."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from peruvian_medical_misinformation.review import review_rows, write_review_csv


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def project_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPOSITORY_ROOT / path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="CSV de candidatas de una corrida.")
    parser.add_argument("--output", help="CSV UTF-8 que se abrirá y completará en Excel.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    candidates_path = project_path(args.input)
    candidates = pd.read_csv(candidates_path, dtype=str, keep_default_na=False)
    required = {"run_id", "record_id", "url", "title", "source_name"}
    missing = sorted(required - set(candidates.columns))
    if missing:
        raise SystemExit("El CSV de candidatas no tiene las columnas requeridas: " + ", ".join(missing))

    output = (
        project_path(args.output)
        if args.output
        else REPOSITORY_ROOT / "data/02_review" / f"{candidates_path.stem}_manual_review.csv"
    )
    rows = review_rows(candidates.to_dict(orient="records"))
    write_review_csv(output, rows)
    print(f"Plantilla manual creada con {len(rows)} filas: {output}")
    print("Completa is_medical, body, evidencia, etiqueta y estado de revisión en Excel y guárdala como CSV UTF-8.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
