#!/usr/bin/env python3
"""Recolecta un manifiesto de URLs públicas y guarda HTML, JSONL y un log CSV."""

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
    parser.add_argument(
        "--urls-file", default="data/raw/source_urls_candidates_pending_period.csv"
    )
    parser.add_argument("--output", default="data/interim/scraped_news.jsonl")
    parser.add_argument("--raw-html-dir", default="data/raw/html")
    parser.add_argument("--log", default="data/interim/extraction_log.csv")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--backoff", type=float, default=2.0)
    parser.add_argument("--max-urls", type=int, default=0)
    parser.add_argument(
        "--resume",
        action="store_true",
        help="continúa desde el JSONL existente sin repetir URLs ya registradas",
    )
    parser.add_argument(
        "--user-agent",
        default="peruvian-medical-misinformation-research/0.1 (academic corpus; respectful rate limit)",
    )
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


LOG_FIELDS = [
    "record_id",
    "source_dataset",
    "source_id",
    "source_name",
    "url",
    "canonical_url",
    "retrieved_at",
    "published_at",
    "http_status",
    "content_status",
    "extraction_status",
    "exclusion_reason",
    "scraping_method",
    "raw_html_path",
    "content_hash",
    "normalized_content_hash",
    "attempts",
    "error",
]


def _is_retryable(record: dict[str, Any]) -> bool:
    if record.get("content_status") != "http_error":
        return False
    status = record.get("http_status")
    return status is None or (isinstance(status, int) and status in {408, 429}) or (
        isinstance(status, int) and 500 <= status <= 599
    )


def _completed_urls(path: Path) -> set[str]:
    if not path.exists():
        return set()
    completed: set[str] = set()
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            canonical = str(record.get("canonical_url", "") or "")
            if canonical:
                completed.add(canonical)
    return completed


def main() -> int:
    args = parse_args()
    config_path = Path(args.config)
    manifest_path = Path(args.urls_file)
    output_path = Path(args.output)
    raw_html_dir = Path(args.raw_html_dir)
    log_path = Path(args.log)

    try:
        sources = load_sources(config_path)
        rows = load_manifest(manifest_path)
    except (OSError, ValueError, yaml.YAMLError) as error:
        print(f"Error de configuración: {error}", file=sys.stderr)
        return 2

    seen_urls: set[str] = set()
    completed_urls = _completed_urls(output_path) if args.resume else set()
    jobs: list[tuple[dict[str, str], str, dict[str, Any]]] = []
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
        if normalized in completed_urls:
            continue
        jobs.append((row, source_id, source))

    if args.max_urls > 0:
        jobs = jobs[: args.max_urls]

    print(f"URLs válidas para procesar: {len(jobs)}; omitidas: {rejected}")
    if args.dry_run:
        return 0

    output_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    raw_html_dir.mkdir(parents=True, exist_ok=True)
    headers = {"User-Agent": args.user_agent, "Accept": "text/html,application/xhtml+xml"}
    counts: dict[str, int] = {}
    output_mode = "a" if args.resume and output_path.exists() else "w"
    log_mode = "a" if args.resume and log_path.exists() else "w"
    with (
        httpx.Client(headers=headers, follow_redirects=True, timeout=args.timeout) as client,
        output_path.open(output_mode, encoding="utf-8") as jsonl_handle,
        log_path.open(log_mode, newline="", encoding="utf-8") as log_handle,
    ):
        log_writer = csv.DictWriter(log_handle, fieldnames=LOG_FIELDS, extrasaction="ignore")
        if log_mode == "w":
            log_writer.writeheader()
        for index, (row, source_id, source) in enumerate(jobs):
            url = (row.get("url") or "").strip()
            attempts = 1
            record = collect_url(
                client,
                url=url,
                source_id=source_id,
                source_name=str(source.get("name", source_id)),
                allowed_domains=list(source.get("allowed_domains", [])),
                source_dataset=f"scraped_{source_id}",
                raw_html_dir=raw_html_dir,
            )
            while _is_retryable(record) and attempts <= args.retries:
                time.sleep(args.backoff ** attempts)
                attempts += 1
                record = collect_url(
                    client,
                    url=url,
                    source_id=source_id,
                    source_name=str(source.get("name", source_id)),
                    allowed_domains=list(source.get("allowed_domains", [])),
                    source_dataset=f"scraped_{source_id}",
                    raw_html_dir=raw_html_dir,
                )

            record["attempts"] = attempts
            record["source_type"] = row.get("source_type", "")
            record["discovery_method"] = row.get("discovery_method", "")
            record["topic"] = row.get("topic", "")
            record["manifest_candidate_status"] = row.get("candidate_status", "")
            record["manifest_notes"] = row.get("notes", "")
            jsonl_handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            jsonl_handle.flush()
            log_writer.writerow(record)
            log_handle.flush()
            status = str(record["content_status"])
            counts[status] = counts.get(status, 0) + 1
            print(
                f"[{index + 1}/{len(jobs)}] {status} "
                f"{record['canonical_url'] or url} (intentos: {attempts})"
            )
            if args.delay and index + 1 < len(jobs):
                time.sleep(args.delay)

    print(f"Registros escritos: {output_path}")
    print(f"Log escrito: {log_path}")
    print(f"Estados: {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
