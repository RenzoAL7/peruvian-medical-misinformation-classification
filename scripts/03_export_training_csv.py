#!/usr/bin/env python3
"""Exporta el CSV real binario después de la revisión humana completa."""

from __future__ import annotations

import argparse
from pathlib import Path

from peruvian_medical_misinformation.review import (
    read_review_table,
    review_to_training_rows,
    write_training_csv,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def project_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPOSITORY_ROOT / path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="CSV UTF-8 de revisión manual completado.")
    parser.add_argument(
        "--output",
        default="data/processed/training_corpus_real.csv",
        help="CSV binario de noticias reales para la futura fase de entrenamiento.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    review = read_review_table(project_path(args.input))
    rows, errors = review_to_training_rows(review)
    if errors:
        raise SystemExit("No se exportó el corpus. Corrige la revisión:\n- " + "\n- ".join(errors))
    if not rows:
        raise SystemExit("No hay filas binarias completas para exportar.")
    output = project_path(args.output)
    write_training_csv(output, rows)
    print(f"Corpus real binario guardado con {len(rows)} filas: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
