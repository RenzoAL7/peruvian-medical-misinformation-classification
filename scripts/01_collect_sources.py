#!/usr/bin/env python3
"""Recolecta URLs explícitas de fuentes permitidas y escribe registros JSONL."""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path
from typing import Any

import httpx
import yaml

from peruvian_medical_misinformation.collection import canonicalize_url, collect_url


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/sources.yaml")
    parser.add_argument("--urls-file", default="data/raw/source_urls.csv")
    parser.add_argument("--output", default="data/raw/articles.jsonl")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--delay", type=float, default=0.5)
    parser.add_argument("--max-urls", type=int, default=0)
    parser.add_argument("--user-agent", default="peruvian-medical-misinformation-research/0.1")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def load_sources(path: Path) -> dict[str, dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        document = yaml.safe_load(handle) or {}
    sources = document.get("sources", {})
    if not isinstance(sources, dict):
        raise ValueError("configs/sources.yaml debe contener un mapa 'sources'")
    return {str(key): value for key, value in sources.items() if isinstance(value, dict)}


def load_manifest(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if "url" not in (reader.fieldnames or []):
            raise ValueError("El manifiesto debe incluir una columna 'url'")
        rows = list(reader)
    if not rows:
        return []
    return rows


def main() -> int:
    args = parse_args()
    config_path = Path(args.config)
    manifest_path = Path(args.urls_file)
    output_path = Path(args.output)

    try:
        sources = load_sources(config_path)
        rows = load_manifest(manifest_path)
    except (OSError, ValueError, yaml.YAMLError) as error:
        print(f"Error de configuración: {error}", file=sys.stderr)
        return 2

    seen_urls: set[str] = set()
    jobs: list[tuple[str, str, dict[str, Any]]] = []
    rejected = 0
    for row in rows:
        url = (row.get("url") or "").strip()
        source_id = (row.get("source_id") or "").strip()
        if not url:
            continue
        if not source_id or source_id not in sources:
            rejected += 1
            print(f"Omitida: source_id desconocido para {url}", file=sys.stderr)
            continue
        source = sources[source_id]
        if not source.get("enabled", False):
            rejected += 1
            print(f"Omitida: fuente deshabilitada para {url}", file=sys.stderr)
            continue
        try:
            normalized = canonicalize_url(url)
        except ValueError as error:
            rejected += 1
            print(f"Omitida: {url} ({error})", file=sys.stderr)
            continue
        if normalized in seen_urls:
            continue
        seen_urls.add(normalized)
        jobs.append((url, source_id, source))

    if args.max_urls > 0:
        jobs = jobs[: args.max_urls]

    print(f"URLs válidas para procesar: {len(jobs)}; omitidas: {rejected}")
    if args.dry_run:
        return 0

    output_path.parent.mkdir(parents=True, exist_ok=True)
    headers = {"User-Agent": args.user_agent, "Accept": "text/html,application/xhtml+xml"}
    records: list[dict[str, Any]] = []
    with httpx.Client(headers=headers, follow_redirects=True, timeout=args.timeout) as client:
        for index, (url, source_id, source) in enumerate(jobs):
            record = collect_url(
                client,
                url=url,
                source_id=source_id,
                source_name=str(source.get("name", source_id)),
                allowed_domains=list(source.get("allowed_domains", [])),
            )
            records.append(record)
            print(
                f"[{index + 1}/{len(jobs)}] {record['content_status']} {record['canonical_url'] or url}"
            )
            if args.delay and index + 1 < len(jobs):
                time.sleep(args.delay)

    with output_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    counts: dict[str, int] = {}
    for record in records:
        status = str(record["content_status"])
        counts[status] = counts.get(status, 0) + 1
    print(f"Registros escritos: {output_path}")
    print(f"Estados: {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
