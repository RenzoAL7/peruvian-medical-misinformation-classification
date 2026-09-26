"""Importadores trazables para datos existentes, sin reinterpretar etiquetas."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from .corpus import (
    canonicalize_url,
    detect_language,
    empty_record,
    model_text,
    normalize_date,
    normalize_text,
    record_id,
    text_hash,
)


def _value(row: pd.Series, column: str) -> str:
    value = row.get(column, "")
    if pd.isna(value):
        return ""
    return str(value).strip()


def import_edwin_health_rows(
    source_path: str | Path,
    *,
    sheet_name: str,
    run_id: str,
) -> list[dict[str, Any]]:
    """Importa filas de Salud preservando ``CATEGORY`` como etiqueta original.

    El resultado deja ``label`` fuera del registro de corpus porque la equivalencia
    entre REAL/FAKE original y 0/1 requiere revisión humana y evidencia clínica.
    """

    table = pd.read_excel(source_path, sheet_name=sheet_name)
    required = {"TOPICS", "HEADLINE", "TEXT", "LINK", "CATEGORY"}
    missing = required - set(table.columns)
    if missing:
        raise ValueError(f"La hoja {sheet_name!r} no contiene las columnas: {sorted(missing)}")
    health_rows = table[table["TOPICS"].astype(str).str.strip().str.casefold().eq("salud")]
    records: list[dict[str, Any]] = []
    for row_index, row in health_rows.iterrows():
        title = normalize_text(_value(row, "HEADLINE"))
        body = normalize_text(_value(row, "TEXT"))
        url = _value(row, "LINK")
        source_name = _value(row, "SOURCE") or "Fuente no especificada en Edwin"
        record = empty_record(
            url=url,
            source_dataset="edwin_157",
            source_name=source_name,
            run_id=run_id,
        )
        canonical_url = ""
        try:
            canonical_url = canonicalize_url(url)
        except ValueError:
            pass
        normalized = model_text(title, "", body)
        stable_key = canonical_url or f"edwin-row-{row_index + 2}-{normalized}"
        language = detect_language(normalized)
        status = "valid" if title and body and language == "es" else "needs_review"
        reasons: list[str] = []
        if not title:
            reasons.append("titulo_vacio")
        if not body:
            reasons.append("cuerpo_vacio")
        if language != "es":
            reasons.append("idioma_no_confirmado_espanol")
        record.update(
            record_id=record_id(stable_key),
            canonical_url=canonical_url,
            published_at=normalize_date(_value(row, "Fecha")),
            title=title,
            subtitle_or_bajada="",
            body=body,
            author=_value(row, "Autor"),
            section=_value(row, "TOPICS"),
            language=language,
            scraping_method="provided_dataset",
            content_hash=text_hash("\n\n".join(part for part in (title, body) if part)),
            normalized_text=normalized,
            normalized_content_hash=text_hash(normalized) if normalized else "",
            extraction_status=status,
            exclusion_reason=";".join(reasons),
            source_original_label=_value(row, "CATEGORY"),
            source_row_id=str(row_index + 2),
        )
        records.append(record)
    return records
