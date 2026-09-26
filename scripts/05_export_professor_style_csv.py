#!/usr/bin/env python3
"""Exporta el corpus trazable a la estructura de columnas usada por el profesor.

No hereda ni inventa etiquetas: ``CATEGORY`` queda vacío hasta la revisión
humana. El corpus trazable de entrada se conserva sin cambios.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
from pathlib import Path


OUTPUT_FIELDS = [
    "ID",
    "CATEGORY",
    "TOPICS",
    "SOURCE",
    "Tipo de Fuente",
    "HEADLINE",
    "TEXT",
    "LINK",
    "Certificado de seguridad",
    "Fecha",
    "Hora",
    "Autor",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="data/processed/medical_news_corpus_2026.csv")
    parser.add_argument("--output", default="data/processed/medical_news_professor_style_2026.csv")
    return parser.parse_args()


def publication_date_and_time(value: str) -> tuple[str, str]:
    """Separa una fecha ISO-8601 sin transformar una fecha ausente o inválida."""

    raw_value = (value or "").strip()
    if not raw_value:
        return "", ""
    try:
        parsed = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
    except ValueError:
        return "", ""
    return parsed.date().isoformat(), parsed.strftime("%H:%M:%S%z")


def article_text(row: dict[str, str]) -> str:
    """Conserva la bajada junto al cuerpo para formar el texto de entrada."""

    return "\n\n".join(
        value.strip()
        for value in (row.get("subtitle_or_bajada", ""), row.get("body", ""))
        if value and value.strip()
    )


def map_row(row: dict[str, str]) -> dict[str, str]:
    published_date, published_time = publication_date_and_time(row.get("published_at", ""))
    url = (row.get("url") or "").strip()
    return {
        "ID": (row.get("record_id") or "").strip(),
        "CATEGORY": "",
        "TOPICS": "Salud",
        "SOURCE": (row.get("source_name") or "").strip(),
        "Tipo de Fuente": "Medio de comunicación",
        "HEADLINE": (row.get("title") or "").strip(),
        "TEXT": article_text(row),
        "LINK": url,
        "Certificado de seguridad": "Sí" if url.startswith("https://") else "",
        "Fecha": published_date,
        "Hora": published_time,
        "Autor": (row.get("author") or "").strip(),
    }


def main() -> int:
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    with input_path.open(encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as destination:
        writer = csv.DictWriter(destination, fieldnames=OUTPUT_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(map_row(row) for row in rows)
    print(f"CSV estilo profesor: {output_path} ({len(rows)} registros)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
