"""Artefactos para la revisión humana de relevancia médica y veracidad."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from pathlib import Path
from typing import Iterable, Mapping

import pandas as pd


REVIEW_COLUMNS = [
    "run_id",
    "record_id",
    "source_dataset",
    "source_name",
    "source_domain",
    "url",
    "canonical_url",
    "published_at",
    "title",
    "subtitle_or_bajada",
    "author",
    "newsdata_article_id",
    "api_query",
    "retrieved_at",
    "is_medical",
    "medical_relevance_reason",
    "body",
    "main_medical_claim",
    "evidence_source",
    "evidence_url",
    "evidence_excerpt",
    "label",
    "label_reason",
    "reviewer",
    "review_status",
    "reviewed_at",
]

TRAINING_COLUMNS = [
    "record_id",
    "text",
    "label",
    "source_dataset",
    "source_name",
    "url",
    "published_at",
    "is_synthetic",
]


def review_rows(candidates: Iterable[Mapping[str, object]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for candidate in candidates:
        row = {column: str(candidate.get(column, "") or "") for column in REVIEW_COLUMNS}
        row["subtitle_or_bajada"] = str(candidate.get("description", "") or "")
        row.update(
            is_medical="PENDIENTE",
            medical_relevance_reason="",
            body="",
            main_medical_claim="",
            evidence_source="",
            evidence_url="",
            evidence_excerpt="",
            label="",
            label_reason="",
            reviewer="",
            review_status="PENDIENTE",
            reviewed_at="",
        )
        rows.append(row)
    return rows


def write_review_csv(path: str | Path, rows: Iterable[Mapping[str, str]]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    table = pd.DataFrame(list(rows), columns=REVIEW_COLUMNS)
    table.to_csv(destination, index=False, encoding="utf-8")


def read_review_table(path: str | Path) -> pd.DataFrame:
    source = Path(path)
    if source.suffix.lower() != ".csv":
        raise ValueError("La hoja de revisión debe conservarse como CSV UTF-8")
    table = pd.read_csv(source, dtype=str, keep_default_na=False)
    missing = [column for column in REVIEW_COLUMNS if column not in table.columns]
    if missing:
        raise ValueError("Faltan columnas en la hoja de revisión: " + ", ".join(missing))
    return table.fillna("")


def _yes(value: object) -> bool:
    return str(value).strip().casefold() in {"si", "sí", "yes", "true", "1"}


def _no(value: object) -> bool:
    return str(value).strip().casefold() in {"no", "false", "0"}


def _completed(value: object) -> bool:
    return str(value).strip().casefold() in {"completada", "validada", "approved", "complete"}


def normalize_text(value: object) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(value or ""))).strip()


def review_to_training_rows(table: pd.DataFrame) -> tuple[list[dict[str, str]], list[str]]:
    """Devuelve solo noticias reales completas con etiquetas binarias verificadas."""

    accepted: list[dict[str, str]] = []
    errors: list[str] = []
    seen_urls: set[str] = set()
    seen_text_hashes: set[str] = set()
    for index, row in table.iterrows():
        row_number = index + 2
        if _no(row["is_medical"]):
            continue
        if not _yes(row["is_medical"]):
            errors.append(f"Fila {row_number}: completa is_medical con SI o NO")
            continue
        label = str(row["label"]).strip()
        if label == "EXCLUIDA":
            continue
        if label not in {"0", "1"}:
            errors.append(f"Fila {row_number}: is_medical=SI requiere label 0, 1 o EXCLUIDA")
            continue
        if not _completed(row["review_status"]):
            errors.append(f"Fila {row_number}: falta review_status=COMPLETADA")
            continue
        if not normalize_text(row["main_medical_claim"]):
            errors.append(f"Fila {row_number}: falta main_medical_claim")
            continue
        if not normalize_text(row["evidence_source"]) or not normalize_text(row["evidence_url"]):
            errors.append(f"Fila {row_number}: falta fuente o URL de evidencia")
            continue
        if not normalize_text(row["label_reason"]):
            errors.append(f"Fila {row_number}: falta label_reason")
            continue
        title = normalize_text(row["title"])
        subtitle = normalize_text(row["subtitle_or_bajada"])
        body = normalize_text(row["body"])
        if not body:
            errors.append(f"Fila {row_number}: falta body")
            continue
        url = normalize_text(row["url"])
        canonical_url = normalize_text(row["canonical_url"]) or url
        text = "\n\n".join(value for value in (title, subtitle, body) if value)
        text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if canonical_url in seen_urls or text_hash in seen_text_hashes:
            continue
        seen_urls.add(canonical_url)
        seen_text_hashes.add(text_hash)
        accepted.append(
            {
                "record_id": normalize_text(row["record_id"]),
                "text": text,
                "label": label,
                "source_dataset": normalize_text(row["source_dataset"]),
                "source_name": normalize_text(row["source_name"]),
                "url": url,
                "published_at": normalize_text(row["published_at"]),
                "is_synthetic": "false",
            }
        )
    return accepted, errors


def write_training_csv(path: str | Path, rows: Iterable[Mapping[str, str]]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(list(rows), columns=TRAINING_COLUMNS).to_csv(destination, index=False, encoding="utf-8")
