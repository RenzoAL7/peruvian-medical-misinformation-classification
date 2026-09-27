#!/usr/bin/env python3
"""Muestra el contador e historial local de corridas de NewsData."""

from __future__ import annotations

from pathlib import Path

from peruvian_medical_misinformation.newsdata import read_run_registry


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = REPOSITORY_ROOT / "data/00_control/run_registry.csv"


def main() -> int:
    rows = read_run_registry(REGISTRY_PATH)
    print(f"Corridas registradas: {len(rows)}")
    for row in rows:
        print(
            f"#{row.get('run_number', '?')} {row.get('run_id', '')}: "
            f"{row.get('collected_total', '0')}/{row.get('expected_total', '0')} "
            f"({row.get('status', '')})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
