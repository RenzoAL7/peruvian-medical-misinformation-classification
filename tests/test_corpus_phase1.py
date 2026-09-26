from pathlib import Path

import pytest

from peruvian_medical_misinformation.artifacts import annotation_rows, collection_summary
from peruvian_medical_misinformation.config import (
    ConfigurationError,
    collection_period,
    validate_source_compliance,
)
from peruvian_medical_misinformation.corpus import (
    CORPUS_FIELDS,
    build_article_record,
    canonicalize_url,
    save_versioned_html,
)
from peruvian_medical_misinformation.deduplication import mark_duplicates
from peruvian_medical_misinformation.spiders import scrapy_settings


HTML = """
<html>
  <head>
    <link rel="canonical" href="/salud/noticia-medica?utm_source=ignored" />
    <meta property="og:title" content="Vacuna y salud pública" />
    <meta property="og:description" content="Una bajada verificable" />
    <meta property="article:published_time" content="2025-03-04T12:30:00-05:00" />
    <meta property="article:section" content="Salud" />
    <meta name="author" content="Redacción" />
  </head>
  <body>
    <article>
      <p>La vacunación es una medida de salud pública que ayuda a prevenir enfermedades infecciosas y reduce el riesgo de cuadros graves en la población expuesta.</p>
      <p>La noticia explica que no se deben reemplazar los tratamientos indicados por personal sanitario y conserva información relevante para una revisión humana posterior.</p>
      <p>También recuerda que las decisiones individuales deben considerar síntomas, antecedentes clínicos y recomendaciones de instituciones de salud confiables.</p>
    </article>
  </body>
</html>
"""


def test_phase1_record_has_required_traceability_fields_and_no_label():
    record = build_article_record(
        html=HTML,
        requested_url="https://rpp.pe/salud/noticia-medica?utm_campaign=test",
        response_url="https://rpp.pe/salud/noticia-medica?utm_campaign=test",
        source_dataset="scraped_rpp",
        source_name="RPP Noticias",
        allowed_domains=["rpp.pe"],
        http_status=200,
        run_id="test-run",
    )
    assert set(CORPUS_FIELDS).issubset(record)
    assert record["canonical_url"] == "https://rpp.pe/salud/noticia-medica"
    assert record["source_dataset"] == "scraped_rpp"
    assert record["title"] == "Vacuna y salud pública"
    assert record["subtitle_or_bajada"] == "Una bajada verificable"
    assert record["author"] == "Redacción"
    assert record["section"] == "Salud"
    assert record["extraction_status"] == "valid"
    assert record["normalized_content_hash"]
    assert "label" not in record


def test_extractor_honors_configured_minimum_body_size():
    record = build_article_record(
        html=HTML,
        requested_url="https://rpp.pe/salud/noticia-medica",
        response_url="https://rpp.pe/salud/noticia-medica",
        source_dataset="scraped_rpp",
        source_name="RPP Noticias",
        allowed_domains=["rpp.pe"],
        http_status=200,
        run_id="test-run",
        minimum_body_characters=10_000,
    )
    assert record["extraction_status"] == "excluded"
    assert record["exclusion_reason"] == "contenido_demasiado_corto"


def test_canonicalize_url_removes_tracking_and_sorts_remaining_parameters():
    assert canonicalize_url("https://rpp.pe/a?z=2&utm_source=x&a=1#fragment") == "https://rpp.pe/a?a=1&z=2"


def test_duplicate_marking_preserves_all_rows_and_marks_exact_content():
    first = {
        "record_id": "one",
        "canonical_url": "https://rpp.pe/a",
        "normalized_content_hash": "same",
        "normalized_text": "texto médico suficiente para revisar la evidencia clínica de una noticia.",
        "extraction_status": "valid",
    }
    second = {**first, "record_id": "two", "canonical_url": "https://latina.pe/b"}
    marked = mark_duplicates([first, second])
    assert len(marked) == 2
    assert marked[0]["duplicate_status"] == "unique"
    assert marked[1]["duplicate_status"] == "exact_content"
    assert marked[1]["duplicate_of_record_id"] == "one"


def test_annotation_rows_include_only_valid_unique_records():
    valid = {field: "" for field in CORPUS_FIELDS}
    valid.update(record_id="valid", extraction_status="valid", duplicate_status="unique")
    duplicate = {**valid, "record_id": "duplicate", "duplicate_status": "exact_url"}
    rows = annotation_rows([valid, duplicate])
    assert len(rows) == 1
    assert rows[0]["review_status"] == "pendiente"
    assert rows[0]["label"] == ""


def test_html_storage_versions_previous_capture(tmp_path: Path):
    first = save_versioned_html(
        "<html>uno</html>",
        raw_html_root=tmp_path,
        source_dataset="scraped_rpp",
        article_record_id="abc",
        retrieved_at="2026-01-01T00:00:00+00:00",
    )
    second = save_versioned_html(
        "<html>dos</html>",
        raw_html_root=tmp_path,
        source_dataset="scraped_rpp",
        article_record_id="abc",
        retrieved_at="2026-01-01T00:00:00+00:00",
    )
    assert first != second
    assert first.read_text(encoding="utf-8") == "<html>uno</html>"
    assert second.read_text(encoding="utf-8") == "<html>dos</html>"


def test_missing_period_blocks_scrapy_execution():
    with pytest.raises(ConfigurationError, match="collection.period.start/end"):
        collection_period({"collection": {"period": {"start": None, "end": None}}})


def test_source_marked_not_permitted_blocks_scrapy_execution():
    with pytest.raises(ConfigurationError, match="scrapy_allowed=true"):
        validate_source_compliance(
            {
                "sources": {
                    "rpp": {
                        "enabled": True,
                        "compliance": {
                            "robots_reviewed_at": "2026-09-26",
                            "terms_reviewed_at": "2026-09-26",
                            "scrapy_allowed": False,
                        },
                        "discovery": {"entrypoints": [{"url": "https://rpp.pe/sitemap/web"}]},
                    }
                }
            }
        )


def test_summary_reports_deficit_against_minimum():
    record = {
        "source_dataset": "edwin_157",
        "source_original_label": "VERDADERO",
        "extraction_status": "valid",
        "duplicate_status": "unique",
    }
    summary = collection_summary([record], minimum_records=200)
    assert summary["minimum_reached"] is False
    assert summary["records_missing_to_minimum"] == 199
    assert summary["valid_unique_by_source_dataset"] == {"edwin_157": 1}
    assert summary["missing_field_counts"]["title"] == 1
    assert summary["source_original_label_counts"] == {"edwin_157": {"VERDADERO": 1}}
    assert summary["label_semantics_status"] == "unmapped_pending_human_evidence_review"


def test_scrapy_settings_obey_robots_and_limit_domain_concurrency():
    settings = scrapy_settings(
        {
            "collection": {
                "robots_txt_obey": True,
                "download_delay_seconds": 1.5,
                "concurrent_requests_per_domain": 1,
                "retry_times": 2,
                "retry_backoff_base_seconds": 2,
                "retry_backoff_max_seconds": 30,
                "max_urls_per_run": 200,
            }
        },
        cache_dir="data/interim/httpcache/test",
    )
    assert settings["ROBOTSTXT_OBEY"] is True
    assert settings["CONCURRENT_REQUESTS_PER_DOMAIN"] == 1
    assert settings["DOWNLOAD_DELAY"] == 1.5
    assert settings["RETRY_BACKOFF_BASE_SECONDS"] == 2
    assert settings["RETRY_BACKOFF_MAX_SECONDS"] == 30
    assert (
        settings["DOWNLOADER_MIDDLEWARES"]
        ["peruvian_medical_misinformation.spiders.ExponentialBackoffRetryMiddleware"]
        == 550
    )
