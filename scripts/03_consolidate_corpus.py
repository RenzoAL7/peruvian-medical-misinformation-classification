#!/usr/bin/env python3
"""Consolida fuentes existentes y scrapeadas en CSV, Parquet y un resumen auditable."""

from __future__ import annotations

import argparse
from pathlib import Path

from peruvian_medical_misinformation.artifacts import (
    collection_summary,
    consolidate_records,
    load_jsonl,
    write_corpus,
    write_extraction_log,
    write_summary,
)
from peruvian_medical_misinformation.config import load_yaml


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-config", default="configs/base.yaml")
    parser.add_argument("--edwin-records", default="data/raw/metadata/edwin_157.jsonl")
    parser.add_argument("--scraped-records", default="data/interim/scraped_news.jsonl")
    parser.add_argument("--csv-output", default="")
    parser.add_argument("--parquet-output", default="")
    parser.add_argument("--log-output", default="")
    parser.add_argument("--summary-output", default="")
    parser.add_argument("--require-minimum", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_yaml(args.base_config)
    data_config = config["data"]
    corpus_config = config["corpus"]
    records = load_jsonl(args.edwin_records) + load_jsonl(args.scraped_records)
    if not records:
        raise SystemExit("No hay registros para consolidar. Importa Edwin o ejecuta una colección autorizada.")
    consolidated = consolidate_records(
        records,
        near_duplicate_threshold=float(config.get("collection", {}).get("near_duplicate_threshold", 0.92)),
    )
    csv_output = args.csv_output or data_config["corpus_csv"]
    parquet_output = args.parquet_output or data_config["corpus_parquet"]
    write_corpus(consolidated, csv_path=csv_output, parquet_path=parquet_output)
    log_output = args.log_output or data_config["extraction_log"]
    write_extraction_log(log_output, consolidated)
    summary = collection_summary(
        consolidated,
        minimum_records=int(corpus_config.get("minimum_records_before_annotation", 200)),
    )
    write_summary(args.summary_output or data_config["collection_summary"], summary)
    print(f"CSV: {csv_output}")
    print(f"Parquet: {parquet_output}")
    print(f"Log consolidado: {log_output}")
    print(f"Resumen: {args.summary_output or data_config['collection_summary']}")
    print(summary)
    if args.require_minimum and not summary["minimum_reached"]:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
