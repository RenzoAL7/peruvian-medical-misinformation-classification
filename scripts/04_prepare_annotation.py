#!/usr/bin/env python3
"""Genera una plantilla HITL; nunca asigna por sí sola las etiquetas finales."""

from __future__ import annotations

import argparse

import pandas as pd

from peruvian_medical_misinformation.artifacts import annotation_rows, write_annotation_template
from peruvian_medical_misinformation.config import load_yaml


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-config", default="configs/base.yaml")
    parser.add_argument("--input", default="")
    parser.add_argument("--output", default="")
    parser.add_argument("--allow-below-minimum", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_yaml(args.base_config)
    data_config = config["data"]
    corpus_config = config["corpus"]
    input_path = args.input or data_config["corpus_csv"]
    table = pd.read_csv(input_path, keep_default_na=False)
    rows = annotation_rows(table.to_dict(orient="records"))
    minimum = int(corpus_config.get("minimum_records_before_annotation", 200))
    if len(rows) < minimum and not args.allow_below_minimum:
        raise SystemExit(
            f"Solo hay {len(rows)} registros válidos y únicos; se requieren {minimum}. "
            "Usa --allow-below-minimum únicamente para un piloto de revisión."
        )
    output = args.output or data_config["annotation_template"]
    write_annotation_template(output, rows)
    print(f"Plantilla HITL escrita: {output} ({len(rows)} registros)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
