from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from peruvian_medical_misinformation.newsdata import (
    NewsDataRateLimitError,
    archive_candidates_from_html,
    append_run_registry,
    collect_candidates,
    next_run_number,
    read_run_registry,
    run_status,
)


def test_archive_candidates_keep_article_links_and_ignore_navigation() -> None:
    source = {"name": "Latina Noticias", "source_dataset": "archive_latina", "domain": "latinanoticias.pe"}
    html = """
    <section id="principal">
      <figure class="main-card"><a href="/te-ayudo/mitos-sobre-el-cancer_20260808/"><img alt="Mitos sobre el cáncer" /></a></figure>
      <figure class="main-card"><a href="https://latinanoticias.pe/lima/hospital-en-crisis_20260306/">Hospital en crisis</a></figure>
    </section>
    <a href="https://latinanoticias.pe/deportes/partido_20260306/">Navegación</a>
    """

    rows = archive_candidates_from_html(
        html,
        archive_url="https://latinanoticias.pe/noticias-sobre/medicina/",
        source_id="latina",
        source=source,
        run_id="test_run",
        retrieved_at="2026-09-27T00:00:00+00:00",
    )

    assert [(row["title"], row["source_dataset"]) for row in rows] == [
        ("Mitos sobre el cáncer", "archive_latina"),
        ("Hospital en crisis", "archive_latina"),
    ]


def test_collect_candidates_uses_archive_source_without_api_request() -> None:
    config = {
        "batch": {
            "endpoint": "https://example.test/latest",
            "output_dir": "data/01_candidates",
            "report_dir": "reports/runs",
            "expected_total": 2,
            "per_source_limit": 2,
            "health_queries": ["salud"],
        },
        "sources": {
            "latina": {
                "name": "Latina Noticias",
                "source_dataset": "archive_latina",
                "domain": "latinanoticias.pe",
                "discovery": "archive",
                "archive_urls": ["https://latinanoticias.pe/noticias-sobre/salud/"],
            }
        },
    }
    html = """
    <section id="principal">
      <figure class="main-card"><a href="/lima/salud-uno_20260901/">Salud uno</a></figure>
      <figure class="main-card"><a href="/lima/salud-dos_20260902/">Salud dos</a></figure>
    </section>
    """

    rows, summary = collect_candidates(
        config,
        api_key="secret",
        run_id="test_run",
        request_json=lambda *_: (_ for _ in ()).throw(AssertionError("No debe llamar a la API")),
        request_html=lambda _: html,
        sleep=lambda _: None,
    )

    assert len(rows) == 2
    assert summary["total_requests"] == 0
    assert summary["archive_requests_total"] == 1
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
