"""Marcado reproducible de duplicados sin eliminar los registros originales."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-záéíóúüñ]{3,}", (text or "").casefold()))


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def mark_duplicates(records: Iterable[dict[str, Any]], near_threshold: float = 0.92) -> list[dict[str, Any]]:
    """Marca URL, texto exacto y casos casi idénticos, preservando todas las filas."""

    prepared = [dict(record) for record in records]
    by_url: dict[str, dict[str, Any]] = {}
    by_hash: dict[str, dict[str, Any]] = {}
    candidates: list[dict[str, Any]] = []

    for record in prepared:
        if record.get("duplicate_status") in {None, "", "not_checked"}:
            record["duplicate_status"] = "unique"
        record.setdefault("duplicate_of_record_id", "")
        record.setdefault("duplicate_similarity", "")
        canonical = str(record.get("canonical_url") or "")
        content_hash = str(record.get("normalized_content_hash") or record.get("content_hash") or "")
        first = by_url.get(canonical) if canonical else None
        if first:
            record.update(
                duplicate_status="exact_url",
                duplicate_of_record_id=first.get("record_id", ""),
                duplicate_similarity="1.000",
            )
            continue
        if canonical:
            by_url[canonical] = record
        first = by_hash.get(content_hash) if content_hash else None
        if first:
            record.update(
                duplicate_status="exact_content",
                duplicate_of_record_id=first.get("record_id", ""),
                duplicate_similarity="1.000",
            )
            continue
        if content_hash:
            by_hash[content_hash] = record
        candidates.append(record)

    token_cache = [(record, _tokens(str(record.get("normalized_text") or record.get("body") or ""))) for record in candidates]
    for index, (record, tokens) in enumerate(token_cache):
        if record.get("duplicate_status") != "unique" or len(tokens) < 12:
            continue
        for previous, previous_tokens in token_cache[:index]:
            if previous.get("duplicate_status") != "unique" or len(previous_tokens) < 12:
                continue
            similarity = _jaccard(tokens, previous_tokens)
            if similarity >= near_threshold:
                record.update(
                    duplicate_status="near_duplicate",
                    duplicate_of_record_id=previous.get("record_id", ""),
                    duplicate_similarity=f"{similarity:.3f}",
                )
                break
    return prepared
