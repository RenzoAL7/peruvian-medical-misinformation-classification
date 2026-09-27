#!/usr/bin/env python3
"""Recolecta un batch de candidatas de NewsData.io.

La salida contiene únicamente metadatos de descubrimiento (URL, título, fecha y
fuente). Este script no descarga cuerpos ni decide relevancia médica o
veracidad.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from peruvian_medical_misinformation.newsdata import (
    NewsDataConfigurationError,
    api_key_from_environment,
    collect_candidates,
    httpx_json_request,
    load_local_env,
    load_yaml,
    read_candidates,
    validate_batch_config,
    write_candidates,
    write_summary,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def project_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPOSITORY_ROOT / path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default="configs/batch_60.yaml",
        help="Configuración YAML relativa al repositorio.",
    )
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Archivo local con NEWSDATA_API_KEY. No se versiona.",
    )
    parser.add_argument("--run-id", help="Identificador de corrida reproducible.")
    parser.add_argument(
        "--resume-from",
        help="CSV de una corrida parcial para completar solo los faltantes por fuente.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Valida y muestra el alcance sin contactar la API.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_path = project_path(args.config)
    config = load_yaml(config_path)
    batch, sources = validate_batch_config(config)

    seeded_rows = read_candidates(project_path(args.resume_from)) if args.resume_from else []

    if args.dry_run:
        print(
            "Configuración válida: "
            f"{batch['expected_total']} candidatas = "
            f"{batch['per_source_limit']} por cada una de {len(sources)} fuentes."
        )
        if seeded_rows:
            print(f"La reanudación conservaría {len(seeded_rows)} candidatas previas.")
        print("No se hicieron solicitudes a NewsData.io.")
        return 0

    load_local_env(project_path(args.env_file))
    api_key = api_key_from_environment()
    run_id = args.run_id or datetime.now(timezone.utc).strftime("newsdata_%Y%m%dT%H%M%SZ")

    rows, summary = collect_candidates(
        config,
        api_key=api_key,
        run_id=run_id,
        request_json=httpx_json_request(float(batch["timeout_seconds"])),
        seeded_rows=seeded_rows,
    )
    summary["config_path"] = str(config_path.relative_to(REPOSITORY_ROOT))
    summary["executed_at"] = datetime.now(timezone.utc).isoformat()
    if args.resume_from:
        summary["resumed_from"] = str(project_path(args.resume_from).relative_to(REPOSITORY_ROOT))

    candidates_path = project_path(batch["output_dir"]) / f"{run_id}.csv"
    summary_path = project_path(batch["report_dir"]) / f"{run_id}.json"
    write_candidates(candidates_path, rows)
    write_summary(summary_path, summary)

    print(f"Candidatas guardadas: {len(rows)}/{batch['expected_total']} en {candidates_path}")
    if summary["seeded_total"]:
        print(f"Candidatas conservadas desde una corrida previa: {summary['seeded_total']}")
    for source_id, counts in summary["per_source"].items():
        print(f"- {source_id}: {counts['collected']}/{counts['requested']}")
    if summary["shortfall_total"]:
        print("La API no devolvió suficientes candidatas para completar el batch; no se inventaron URLs.")
    if summary["rate_limited"]:
        print("La API alcanzó su límite temporal. Espera el reinicio de NewsData y ejecuta una nueva corrida.")
    if summary["errors"]:
        print(f"Se registraron {len(summary['errors'])} errores en {summary_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except NewsDataConfigurationError as error:
        raise SystemExit(f"Configuración inválida: {error}") from error
