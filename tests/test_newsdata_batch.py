from __future__ import annotations

from datetime import datetime, timezone

from peruvian_medical_misinformation.newsdata import (
    NewsDataRateLimitError,
    archive_candidates_from_html,
    append_run_registry,
    canonicalize_url,
    collect_candidates,
    next_run_number,
    read_record_ids,
    read_run_registry,
    record_id,
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


def test_archive_candidates_support_peru21_card_selector_and_title_preference() -> None:
    source = {
        "name": "Perú21",
        "source_dataset": "archive_peru21",
        "domain": "peru21.pe",
        "article_link_selector": "div.view-content article a[href]",
        "allow_selected_article_urls": True,
        "candidate_keywords": ["salud", "higado"],
    }
    html = """
    <div class="view-content"><article>
      <a href="/vida/factores-de-riesgo-salud-higado/"><img alt="Imagen" /></a>
      <a href="/vida/factores-de-riesgo-salud-higado/">Factores de riesgo para la salud del hígado</a>
    </article></div>
    <a href="/noticias/salud/2/">Siguiente página</a>
    """

    rows = archive_candidates_from_html(
        html,
        archive_url="https://peru21.pe/noticias/salud/",
        source_id="peru21",
        source=source,
        run_id="test_run",
        retrieved_at="2026-09-27T00:00:00+00:00",
    )

    assert [(row["title"], row["canonical_url"]) for row in rows] == [
        ("Factores de riesgo para la salud del hígado", "https://peru21.pe/vida/factores-de-riesgo-salud-higado/"),
    ]


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


def test_collect_candidates_skips_sheet_duplicates_and_tries_next_query() -> None:
    config = {
        "batch": {
            "endpoint": "https://example.test/latest",
            "output_dir": "data/01_candidates",
            "report_dir": "reports/runs",
            "expected_total": 2,
            "per_source_limit": 2,
            "results_per_request": 10,
            "health_queries": ["medicina", "salud"],
            "max_requests_per_source": 2,
            "max_requests_total": 2,
        },
        "sources": {
            "rpp": {"name": "RPP Noticias", "source_dataset": "newsdata_rpp", "domain": "rpp.pe"}
        },
    }
    existing_url = canonicalize_url("https://rpp.pe/salud/repetida")
    calls: list[dict[str, str]] = []

    def fake_request(_: str, params: dict[str, str]) -> dict[str, object]:
        calls.append(params)
        if params["q"] == "medicina":
            return {
                "status": "success",
                "results": [{"link": existing_url, "title": "Ya estaba en la hoja"}],
            }
        return {
            "status": "success",
            "results": [
                {"link": "https://rpp.pe/salud/nueva-uno", "title": "Nueva uno"},
                {"link": "https://rpp.pe/salud/nueva-dos", "title": "Nueva dos"},
            ],
        }

    rows, summary = collect_candidates(
        config,
        api_key="secret",
        run_id="test_run",
        request_json=fake_request,
        excluded_record_ids={record_id(existing_url)},
        sleep=lambda _: None,
    )

    assert [call["q"] for call in calls] == ["medicina", "salud"]
    assert all(call["size"] == "10" for call in calls)
    assert all(call["removeduplicate"] == "1" for call in calls)
    assert all(call["video"] == "0" for call in calls)
    assert {row["title"] for row in rows} == {"Nueva uno", "Nueva dos"}
    assert summary["duplicates_skipped_total"] == 1
    assert summary["per_source"]["rpp"]["duplicates_skipped"] == 1


def test_archive_filters_section_root_and_non_medical_titles() -> None:
    batch = {
        "candidate_keywords": ["cáncer", "vacuna"],
        "candidate_claim_keywords": ["riesgo", "previene"],
    }
    source = {
        "name": "Diario Correo",
        "source_dataset": "archive_correo_salud",
        "domain": "diariocorreo.pe",
        "article_url_prefixes": ["/salud/"],
        "article_link_selector": "a[href*='/salud/']",
    }
    html = """
    <a href="/salud/">Portada de salud</a>
    <a href="/salud/cancer-senales-noticia/">Cáncer: señales que aumentan el riesgo</a>
    <a href="/salud/concurso-alimentacion-noticia/">Concurso de alimentación en Lima</a>
    <a href="/politica/vacuna-noticia/">Vacuna debatida en el Congreso</a>
    """

    rows = archive_candidates_from_html(
        html,
        archive_url="https://diariocorreo.pe/salud/",
        source_id="correo",
        source=source,
        run_id="test_run",
        retrieved_at="2026-09-29T00:00:00+00:00",
        batch=batch,
    )

    assert [row["title"] for row in rows] == ["Cáncer: señales que aumentan el riesgo"]


def test_archive_fallback_does_not_duplicate_partial_archive_result() -> None:
    config = {
        "batch": {
            "endpoint": "https://example.test/latest",
            "output_dir": "data/01_candidates",
            "report_dir": "reports/runs",
            "expected_total": 2,
            "per_source_limit": 2,
            "health_queries": ["salud"],
            "max_requests_per_source": 2,
            "max_requests_total": 2,
        },
        "sources": {
            "latina": {
                "name": "Latina Noticias",
                "source_dataset": "archive_latina",
                "newsdata_source_dataset": "newsdata_latina",
                "domain": "latinanoticias.pe",
                "discovery": "archive",
                "newsdata_fallback": True,
                "archive_urls": ["https://latinanoticias.pe/noticias-sobre/salud/"],
            }
        },
    }
    html = """
    <section id="principal">
      <figure class="main-card"><a href="/lima/salud-uno_20260901/">Salud uno</a></figure>
    </section>
    """

    rows, summary = collect_candidates(
        config,
        api_key="secret",
        run_id="test_run",
        request_json=lambda *_: {
            "status": "success",
            "results": [{"link": "https://latinanoticias.pe/lima/salud-dos_20260902/", "title": "Salud dos"}],
        },
        request_html=lambda _: html,
        sleep=lambda _: None,
    )

    assert len(rows) == 2
    assert len({row["record_id"] for row in rows}) == 2
    assert summary["collected_total"] == 2


def test_read_record_ids_from_sheet_export(tmp_path) -> None:
    exported = tmp_path / "raw.csv"
    exported.write_text("record_id,title\nabc,Uno\nabc,Duplicada\ndef,Dos\n", encoding="utf-8-sig")

    assert read_record_ids(exported) == {"abc", "def"}


def test_read_record_ids_from_excel_raw_sheet(tmp_path) -> None:
    from openpyxl import Workbook

    exported = tmp_path / "revision.xlsx"
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Raw"
    worksheet.append(["run_id", "record_id", "title"])
    worksheet.append(["run_1", "abc", "Uno"])
    worksheet.append(["run_2", "abc", "Duplicada"])
    worksheet.append(["run_3", "def", "Dos"])
    workbook.save(exported)

    assert read_record_ids(exported) == {"abc", "def"}


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


def test_collect_candidates_finishes_public_archives_before_api_rate_limit() -> None:
    config = {
        "batch": {
            "endpoint": "https://example.test/latest",
            "output_dir": "data/01_candidates",
            "report_dir": "reports/runs",
            "expected_total": 2,
            "per_source_limit": 1,
            "health_queries": ["salud"],
            "max_requests_per_source": 1,
            "max_requests_total": 2,
        },
        "sources": {
            "rpp": {"name": "RPP Noticias", "source_dataset": "newsdata_rpp", "domain": "rpp.pe"},
            "latina": {
                "name": "Latina Noticias",
                "source_dataset": "archive_latina",
                "domain": "latinanoticias.pe",
                "discovery": "archive",
                "archive_urls": ["https://latinanoticias.pe/noticias-sobre/salud/"],
            },
        },
    }
    html = """
    <section id="principal">
      <figure class="main-card"><a href="/lima/salud-nueva_20260928/">Salud nueva</a></figure>
    </section>
    """

    rows, summary = collect_candidates(
        config,
        api_key="secret",
        run_id="test_run",
        request_json=lambda *_: (_ for _ in ()).throw(NewsDataRateLimitError("Rate limit exceeded")),
        request_html=lambda _: html,
        sleep=lambda _: None,
    )

    assert [(row["source_id"], row["title"]) for row in rows] == [("latina", "Salud nueva")]
    assert summary["rate_limited"] is True
    assert summary["per_source"]["latina"]["status"] == "completed"
    assert summary["per_source"]["rpp"]["status"] == "rate_limited"


def test_collect_candidates_shares_request_budget_between_sources_by_topic_round() -> None:
    config = {
        "batch": {
            "endpoint": "https://example.test/latest",
            "output_dir": "data/01_candidates",
            "report_dir": "reports/runs",
            "expected_total": 2,
            "per_source_limit": 1,
            "health_queries": ["salud", "medicina"],
            "max_requests_per_source": 2,
            "max_requests_total": 2,
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
    calls: list[tuple[str, str]] = []

    def empty_request(_: str, params: dict[str, str]) -> dict[str, object]:
        calls.append((params["domainurl"], params["q"]))
        return {"status": "success", "results": []}

    rows, summary = collect_candidates(
        config,
        api_key="secret",
        run_id="test_run",
        request_json=empty_request,
        sleep=lambda _: None,
    )

    assert rows == []
    assert calls == [("rpp.pe", "salud"), ("elcomercio.pe", "salud")]
    assert summary["request_budget_exhausted"] is True
    assert summary["per_source"]["rpp"]["api_requests"] == 1
    assert summary["per_source"]["comercio"]["api_requests"] == 1


def test_collect_candidates_rotates_the_first_medical_topic() -> None:
    config = {
        "batch": {
            "endpoint": "https://example.test/latest",
            "output_dir": "data/01_candidates",
            "report_dir": "reports/runs",
            "expected_total": 1,
            "per_source_limit": 1,
            "health_queries": ["salud", "medicina", "cáncer"],
            "max_requests_per_source": 1,
            "max_requests_total": 1,
        },
        "sources": {
            "rpp": {"name": "RPP Noticias", "source_dataset": "newsdata_rpp", "domain": "rpp.pe"}
        },
    }
    calls: list[str] = []

    def empty_request(_: str, params: dict[str, str]) -> dict[str, object]:
        calls.append(params["q"])
        return {"status": "success", "results": []}

    _, summary = collect_candidates(
        config,
        api_key="secret",
        run_id="test_run",
        request_json=empty_request,
        query_offset=1,
        sleep=lambda _: None,
    )

    assert calls == ["medicina"]
    assert summary["query_order"] == ["medicina", "cáncer", "salud"]
    assert summary["query_offset"] == 1


def test_collect_candidates_keeps_grouped_queries_first_when_topics_rotate() -> None:
    grouped = "(salud OR medicina OR enfermedad)"
    config = {
        "batch": {
            "endpoint": "https://example.test/latest",
            "output_dir": "data/01_candidates",
            "report_dir": "reports/runs",
            "expected_total": 1,
            "per_source_limit": 1,
            "health_queries": [grouped, "salud", "medicina", "cáncer"],
            "priority_query_count": 1,
            "max_requests_per_source": 4,
            "max_requests_total": 4,
        },
        "sources": {
            "rpp": {"name": "RPP Noticias", "source_dataset": "newsdata_rpp", "domain": "rpp.pe"}
        },
    }
    calls: list[str] = []

    def empty_request(_: str, params: dict[str, str]) -> dict[str, object]:
        calls.append(params["q"])
        return {"status": "success", "results": []}

    _, summary = collect_candidates(
        config,
        api_key="secret",
        run_id="test_run",
        request_json=empty_request,
        query_offset=1,
        sleep=lambda _: None,
    )

    assert calls == [grouped, "medicina", "cáncer", "salud"]
    assert summary["query_order"] == calls
    assert summary["query_offset"] == 1


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
