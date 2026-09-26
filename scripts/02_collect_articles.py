#!/usr/bin/env python3
"""Extrae artículos desde el manifiesto descubierto usando Scrapy y Trafilatura."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from scrapy.crawler import CrawlerProcess

from peruvian_medical_misinformation.config import collection_period, load_yaml, validate_source_compliance
from peruvian_medical_misinformation.spiders import ArticleCollectionSpider, scrapy_settings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-config", default="configs/base.yaml")
    parser.add_argument("--sources-config", default="configs/sources.yaml")
    parser.add_argument("--urls-file", default="")
    parser.add_argument("--output", default="")
    parser.add_argument("--log", default="")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--max-urls", type=int, default=0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    base_config = load_yaml(args.base_config)
    sources_config = load_yaml(args.sources_config)
    period_start, period_end = collection_period(base_config)
    validate_source_compliance(sources_config)
    data_config = base_config.get("data", {})
    urls_file = Path(args.urls_file or data_config["discovered_urls"])
    if not urls_file.exists():
        raise SystemExit(f"No existe el manifiesto de URLs: {urls_file}")
    run_id = args.run_id or f"scrape_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    output = Path(args.output or data_config["collected_records"])
    log = Path(args.log or data_config["extraction_log"])
    metadata = Path(data_config["raw_metadata_dir"]) / f"{run_id}.jsonl"
    max_urls = args.max_urls or int(base_config.get("collection", {}).get("max_urls_per_run", 300))
    settings = scrapy_settings(base_config, cache_dir="data/interim/httpcache/articles")
    settings["CLOSESPIDER_PAGECOUNT"] = max_urls
    process = CrawlerProcess(settings=settings)
    process.crawl(
        ArticleCollectionSpider,
        sources_config=sources_config,
        urls_file=str(urls_file),
        output_path=str(output),
        log_path=str(log),
        metadata_path=str(metadata),
        raw_html_root=str(data_config["raw_html_dir"]),
        project_root=str(Path.cwd()),
        run_id=run_id,
        period_start=period_start.isoformat(),
        period_end=period_end.isoformat(),
        max_urls=max_urls,
        minimum_body_characters=int(base_config.get("collection", {}).get("minimum_body_characters", 240)),
    )
    process.start()
    print(f"Registros anexados: {output}")
    print(f"Log de extracción: {log}")
    print(f"Metadatos de esta corrida: {metadata}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
