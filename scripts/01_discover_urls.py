#!/usr/bin/env python3
"""Descubre URLs desde categorías, RSS, sitemaps o archivos públicos con Scrapy."""

from __future__ import annotations

import argparse
from pathlib import Path

from scrapy.crawler import CrawlerProcess

from peruvian_medical_misinformation.config import (
    ConfigurationError,
    collection_period,
    load_yaml,
    validate_source_compliance,
)
from peruvian_medical_misinformation.spiders import SourceDiscoverySpider, scrapy_settings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-config", default="configs/base.yaml")
    parser.add_argument("--sources-config", default="configs/sources.yaml")
    parser.add_argument("--output", default="data/interim/discovered_urls.csv")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    base_config = load_yaml(args.base_config)
    sources_config = load_yaml(args.sources_config)
    if args.dry_run:
        print(f"Periodo configurado: {base_config.get('collection', {}).get('period', {})}")
        print(f"Salida propuesta: {args.output}")
        problems: list[str] = []
        try:
            collection_period(base_config)
        except ConfigurationError as error:
            problems.append(str(error))
        try:
            validate_source_compliance(sources_config)
        except ConfigurationError as error:
            problems.append(str(error))
        if problems:
            print("No se iniciará Scrapy:")
            for problem in problems:
                print(f"- {problem}")
        else:
            print("Configuración lista para descubrimiento controlado.")
        return 0
    start, end = collection_period(base_config)
    validate_source_compliance(sources_config)
    print(f"Descubrimiento permitido para el periodo configurado: {start} a {end}")
    settings = scrapy_settings(base_config, cache_dir="data/interim/httpcache/discovery")
    process = CrawlerProcess(settings=settings)
    process.crawl(
        SourceDiscoverySpider,
        sources_config=sources_config,
        keywords=list(base_config.get("collection", {}).get("keywords", [])),
        output_path=str(Path(args.output)),
        max_pages_per_source=int(base_config.get("collection", {}).get("max_discovery_pages_per_source", 30)),
    )
    process.start()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
