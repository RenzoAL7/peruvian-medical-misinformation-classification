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
    append_run_registry,
    api_key_from_environment,
    collect_candidates,
    httpx_json_request,
    httpx_html_request,
    load_local_env,
    load_yaml,
    next_run_number,
    read_candidates,
    read_record_ids,
    read_run_registry,
    run_status,
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
        default="configs/batch_12.yaml",
        help="Configuración YAML relativa al repositorio.",
    )
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Archivo local con NEWSDATA_API_KEY. No se versiona.",
    )
    parser.add_argument("--run-id", help="Identificador opcional; por defecto usa el contador local.")
    parser.add_argument(
        "--resume-from",
        help="CSV de una corrida parcial para completar solo los faltantes por fuente.",
    )
    parser.add_argument(
        "--exclude-record-ids",
        help=(
            "Excel (.xlsx) o CSV con una columna record_id. "
            "Las noticias existentes se omiten y se prueban las siguientes consultas médicas."
        ),
    )
    parser.add_argument(
        "--rotate-queries",
        action="store_true",
        help=(
            "Rota el primer tema médico según la cantidad de record_id excluidos, "
            "para que corridas sucesivas no comiencen siempre por 'salud'."
        ),
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
    registry_path = project_path(batch["run_registry_path"])
    run_number = next_run_number(read_run_registry(registry_path))

    seeded_rows = read_candidates(project_path(args.resume_from)) if args.resume_from else []
    excluded_record_ids = (
        read_record_ids(project_path(args.exclude_record_ids)) if args.exclude_record_ids else set()
    )

    if args.dry_run:
        print(f"Siguiente corrida registrada: #{run_number}")
        print(
            "Configuración válida: "
            f"meta global de {batch['expected_total']} candidatas; "
            f"máximo {batch['per_source_limit']} por cada una de {len(sources)} fuentes."
        )
        if seeded_rows:
            print(f"La reanudación conservaría {len(seeded_rows)} candidatas previas.")
        if excluded_record_ids:
            print(f"Se excluirían {len(excluded_record_ids)} record_id ya presentes en la hoja.")
        print("No se hicieron solicitudes a NewsData.io.")
        return 0

    uses_newsdata = any(
        str(source.get("discovery", "newsdata")) == "newsdata"
        or bool(source.get("newsdata_fallback", False))
        for source in sources.values()
    )
    api_key = ""
    if uses_newsdata:
        load_local_env(project_path(args.env_file))
        api_key = api_key_from_environment()
    run_id = args.run_id or f"run_{run_number:03d}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    configured_queries = [query for query in batch["health_queries"] if str(query).strip()]
    priority_query_count = int(batch.get("priority_query_count", 0))
    rotating_query_count = max(0, len(configured_queries) - priority_query_count)
    query_offset = (
        len(excluded_record_ids) % rotating_query_count
        if args.rotate_queries and rotating_query_count
        else 0
    )

    rows, summary = collect_candidates(
        config,
        api_key=api_key,
        run_id=run_id,
        request_json=httpx_json_request(float(batch["timeout_seconds"])),
        request_html=httpx_html_request(float(batch["timeout_seconds"])),
        seeded_rows=seeded_rows,
        excluded_record_ids=excluded_record_ids,
        query_offset=query_offset,
    )
    summary["config_path"] = str(config_path.relative_to(REPOSITORY_ROOT))
    summary["executed_at"] = datetime.now(timezone.utc).isoformat()
    summary["run_number"] = run_number
    if args.resume_from:
        summary["resumed_from"] = str(project_path(args.resume_from).relative_to(REPOSITORY_ROOT))

    candidates_path = project_path(batch["output_dir"]) / f"{run_id}.csv"
    summary_path = project_path(batch["report_dir"]) / f"{run_id}.json"
    if candidates_path.exists() or summary_path.exists():
        raise NewsDataConfigurationError(
            f"La corrida '{run_id}' ya existe. Elige otro --run-id para no sobrescribir resultados."
        )
    write_candidates(candidates_path, rows)
    write_summary(summary_path, summary)
    append_run_registry(
        registry_path,
        {
            "run_number": run_number,
            "run_id": run_id,
            "executed_at": summary["executed_at"],
            "status": run_status(summary),
            "expected_total": summary["expected_total"],
            "collected_total": summary["collected_total"],
            "shortfall_total": summary["shortfall_total"],
            "total_requests": summary["total_requests"],
            "rate_limited": summary["rate_limited"],
            "request_budget_exhausted": summary["request_budget_exhausted"],
            "seeded_total": summary["seeded_total"],
            "candidates_path": candidates_path.relative_to(REPOSITORY_ROOT),
            "summary_path": summary_path.relative_to(REPOSITORY_ROOT),
            "resumed_from": summary.get("resumed_from", ""),
        },
    )

    print(f"Corrida #{run_number}: {run_id}")
    print(f"Candidatas guardadas: {len(rows)}/{batch['expected_total']} en {candidates_path}")
    if summary["total_requests"]:
        print("Orden de consultas API: " + ", ".join(summary["query_order"]))
    else:
        print("NewsData no se consultó; esta corrida usó únicamente archivos públicos.")
    if summary["seeded_total"]:
        print(f"Candidatas conservadas desde una corrida previa: {summary['seeded_total']}")
    if summary["duplicates_skipped_total"]:
        print(
            "Noticias ya presentes omitidas: "
            f"{summary['duplicates_skipped_total']}; se probaron consultas médicas alternativas."
        )
    for source_id, counts in summary["per_source"].items():
        topics = ", ".join(counts["queries_attempted"]) or "sin consultas API"
        print(
            f"- {source_id}: {counts['collected']} seleccionadas de "
            f"{counts['eligible_discovered']} elegibles (máximo {counts['requested']}) "
            f"[{counts['status']}]; temas: {topics}"
        )
    if summary["shortfall_total"]:
        print("La API no devolvió suficientes candidatas para completar el batch; no se inventaron URLs.")
    if summary["request_budget_exhausted"]:
        print(
            "Se alcanzó el límite interno de solicitudes configurado para esta corrida; "
            "no es el warning de Google Sheets ni necesariamente un límite de NewsData."
        )
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
