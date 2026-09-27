from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from peruvian_medical_misinformation.newsdata import (
    NewsDataRateLimitError,
    append_run_registry,
    collect_candidates,
    next_run_number,
    read_run_registry,
    run_status,
)
from peruvian_medical_misinformation.review import review_rows, review_to_training_rows


def test_collect_candidates_caps_sources_and_filters_domains() -> None:
    config = {
        "batch": {
            "endpoint": "https://example.test/latest",
            "output_dir": "data/raw/source_url_runs",
            "report_dir": "reports/newsdata_runs",
            "expected_total": 4,
            "per_source_limit": 2,
            "language": "es",
            "country": "pe",
            "category": "health",
            "health_queries": ["salud"],
            "max_requests_per_source": 1,
        },
        "sources": {
            "rpp": {"name": "RPP Noticias", "source_dataset": "newsdata_rpp", "domain": "rpp.pe"},
            "comercio": {
                "name": "El Comercio",
                "source_dataset": "newsdata_el_comercio",
                "domain": "elcomercio.pe",
            },
        },
    }
    calls: list[dict[str, str]] = []

    def fake_request(_: str, params: dict[str, str]) -> dict[str, object]:
        calls.append(params)
        domain = params["domainurl"]
        return {
            "status": "success",
            "results": [
                {"link": f"https://{domain}/salud/uno?utm_source=test", "title": "Uno"},
                {"link": f"https://{domain}/salud/uno", "title": "Duplicada"},
                {"link": f"https://{domain}/salud/dos", "title": "Dos", "creator": ["Autor"]},
                {"link": "https://otro.pe/salud/tres", "title": "No corresponde"},
            ],
        }

    rows, summary = collect_candidates(
        config,
        api_key="secret",
        run_id="test_run",
        request_json=fake_request,
        sleep=lambda _: None,
        now=lambda: datetime(2026, 9, 27, tzinfo=timezone.utc),
    )

    assert len(rows) == 4
    assert {row["source_id"] for row in rows} == {"rpp", "comercio"}
    assert all("utm_" not in row["canonical_url"] for row in rows)
    assert {row["author"] for row in rows} >= {"Autor"}
    assert all(call["domainurl"] in {"rpp.pe", "elcomercio.pe"} for call in calls)
    assert summary["shortfall_total"] == 0
    assert summary["total_requests"] == 2


def test_collect_candidates_stops_after_rate_limit() -> None:
    config = {
        "batch": {
            "endpoint": "https://example.test/latest",
            "output_dir": "data/raw/source_url_runs",
            "report_dir": "reports/newsdata_runs",
            "expected_total": 2,
            "per_source_limit": 1,
            "health_queries": ["salud", "medicina"],
            "max_requests_per_source": 2,
            "max_requests_total": 2,
        },
        "sources": {
            "rpp": {"name": "RPP Noticias", "source_dataset": "newsdata_rpp", "domain": "rpp.pe"},
            "latina": {"name": "Latina Noticias", "source_dataset": "newsdata_latina", "domain": "latinanoticias.pe"},
        },
    }
    calls = 0

    def limited_request(_: str, __: dict[str, str]) -> dict[str, object]:
        nonlocal calls
        calls += 1
        raise NewsDataRateLimitError("Rate limit exceeded")

    rows, summary = collect_candidates(
        config,
        api_key="secret",
        run_id="test_run",
        request_json=limited_request,
        sleep=lambda _: None,
    )

    assert rows == []
    assert calls == 1
    assert summary["rate_limited"] is True
    assert summary["per_source"]["rpp"]["status"] == "rate_limited"
    assert summary["per_source"]["latina"]["status"] == "not_requested_after_rate_limit"


def test_collect_candidates_resumes_from_existing_source_rows() -> None:
    config = {
        "batch": {
            "endpoint": "https://example.test/latest",
            "output_dir": "data/raw/source_url_runs",
            "report_dir": "reports/newsdata_runs",
            "expected_total": 2,
            "per_source_limit": 2,
            "health_queries": ["salud"],
            "max_requests_per_source": 1,
            "max_requests_total": 2,
        },
        "sources": {
            "rpp": {"name": "RPP Noticias", "source_dataset": "newsdata_rpp", "domain": "rpp.pe"},
        },
    }
    seeded = [{"run_id": "older", "source_id": "rpp", "url": "https://rpp.pe/salud/uno", "title": "Uno"}]

    def fake_request(_: str, __: dict[str, str]) -> dict[str, object]:
        return {"status": "success", "results": [{"link": "https://rpp.pe/salud/dos", "title": "Dos"}]}

    rows, summary = collect_candidates(
        config,
        api_key="secret",
        run_id="new_run",
        request_json=fake_request,
        seeded_rows=seeded,
        sleep=lambda _: None,
    )

    assert [row["canonical_url"] for row in rows] == [
        "https://rpp.pe/salud/dos",
        "https://rpp.pe/salud/uno",
    ]
    assert next(row for row in rows if row["title"] == "Uno")["seeded_from_run_id"] == "older"
    assert summary["seeded_total"] == 1


def test_run_registry_counts_completed_and_partial_runs(tmp_path) -> None:
    registry = tmp_path / "run_registry.csv"
    append_run_registry(
        registry,
        {
            "run_number": 1,
            "run_id": "run_001",
            "expected_total": 12,
            "collected_total": 12,
            "status": "complete",
        },
    )
    append_run_registry(
        registry,
        {
            "run_number": 2,
            "run_id": "run_002",
            "expected_total": 12,
            "collected_total": 7,
            "status": "partial_no_results",
        },
    )

    rows = read_run_registry(registry)

    assert len(rows) == 2
    assert next_run_number(rows) == 3
    assert run_status({"expected_total": 12, "collected_total": 12}) == "complete"
    assert run_status({"expected_total": 12, "collected_total": 7}) == "partial_no_results"


def test_review_export_only_keeps_complete_binary_human_review() -> None:
    candidates = [
        {
            "run_id": "test_run",
            "record_id": "one",
            "source_dataset": "newsdata_rpp",
            "source_name": "RPP Noticias",
            "source_domain": "rpp.pe",
            "url": "https://rpp.pe/salud/uno",
            "canonical_url": "https://rpp.pe/salud/uno",
            "title": "Título",
            "description": "Bajada",
            "author": "Autora",
        },
        {
            "run_id": "test_run",
            "record_id": "two",
            "source_dataset": "newsdata_rpp",
            "source_name": "RPP Noticias",
            "url": "https://rpp.pe/politica/dos",
            "title": "No médica",
        },
    ]
    table = pd.DataFrame(review_rows(candidates))
    table.loc[0, ["is_medical", "body", "main_medical_claim"]] = [
        "SI",
        "Cuerpo de la noticia.",
        "La afirmación médica principal.",
    ]
    table.loc[0, ["evidence_source", "evidence_url", "label", "label_reason", "review_status"]] = [
        "MINSA",
        "https://www.gob.pe/minsa",
        "0",
        "Compatible con la evidencia consultada.",
        "COMPLETADA",
    ]
    table.loc[1, ["is_medical", "review_status"]] = ["NO", "COMPLETADA"]

    rows, errors = review_to_training_rows(table)

    assert errors == []
    assert rows == [
        {
            "record_id": "one",
            "text": "Título\n\nBajada\n\nCuerpo de la noticia.",
            "label": "0",
            "source_dataset": "newsdata_rpp",
            "source_name": "RPP Noticias",
            "url": "https://rpp.pe/salud/uno",
            "published_at": "",
            "is_synthetic": "false",
        }
    ]
