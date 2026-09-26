"""Carga y valida la configuración reproducible de la colección."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import yaml
from dateutil import parser as date_parser


class ConfigurationError(ValueError):
    """La configuración no permite ejecutar una colección segura."""


def load_yaml(path: str | Path) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as handle:
        value = yaml.safe_load(handle) or {}
    if not isinstance(value, dict):
        raise ConfigurationError(f"{path} debe contener un objeto YAML")
    return value


def collection_period(config: dict[str, Any]) -> tuple[date, date]:
    period = config.get("collection", {}).get("period", {})
    if not isinstance(period, dict) or not period.get("start") or not period.get("end"):
        raise ConfigurationError(
            "Falta collection.period.start/end. Define un periodo común antes de ejecutar una extracción masiva."
        )
    try:
        start = date_parser.parse(str(period["start"])).date()
        end = date_parser.parse(str(period["end"])).date()
    except (TypeError, ValueError, OverflowError) as error:
        raise ConfigurationError("collection.period debe usar fechas válidas ISO-8601") from error
    if start > end:
        raise ConfigurationError("collection.period.start no puede ser posterior a end")
    return start, end


def enabled_sources(sources_config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    sources = sources_config.get("sources", {})
    if not isinstance(sources, dict):
        raise ConfigurationError("configs/sources.yaml debe contener un mapa 'sources'")
    return {
        str(source_id): source
        for source_id, source in sources.items()
        if isinstance(source, dict) and source.get("enabled", False)
    }


def validate_source_compliance(sources_config: dict[str, Any]) -> None:
    missing: list[str] = []
    active_sources = enabled_sources(sources_config)
    if not active_sources:
        raise ConfigurationError("No hay fuentes habilitadas para la colección")
    for source_id, source in active_sources.items():
        compliance = source.get("compliance", {})
        if not isinstance(compliance, dict) or not compliance.get("robots_reviewed_at"):
            missing.append(f"{source_id}: robots_reviewed_at")
        if not isinstance(compliance, dict) or not compliance.get("terms_reviewed_at"):
            missing.append(f"{source_id}: terms_reviewed_at")
        if not isinstance(compliance, dict) or compliance.get("scrapy_allowed") is not True:
            missing.append(f"{source_id}: scrapy_allowed=true")
        discovery = source.get("discovery", {})
        entrypoints = discovery.get("entrypoints", []) if isinstance(discovery, dict) else []
        if not entrypoints:
            missing.append(f"{source_id}: discovery.entrypoints")
    if missing:
        joined = ", ".join(missing)
        raise ConfigurationError(
            "No se puede iniciar Scrapy hasta registrar cumplimiento y rutas públicas: " + joined
        )
