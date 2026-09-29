from pathlib import Path

from peruvian_medical_misinformation.newsdata import load_yaml, validate_batch_config


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_batch_12_uses_four_verified_textual_health_sections() -> None:
    config = load_yaml(REPOSITORY_ROOT / "configs" / "batch_12.yaml")
    batch, sources = validate_batch_config(config)

    assert batch["per_source_limit"] == 3
    assert batch["expected_total"] == 12
    assert batch["max_requests_per_source"] == 2
    assert batch["max_requests_total"] == 4
    assert batch["priority_query_count"] == 2
    assert list(sources) == [
        "el_comercio",
        "la_republica",
        "correo",
        "ojo",
    ]
    assert all(source["discovery"] == "archive" for source in sources.values())
    assert all(source.get("newsdata_fallback", False) is False for source in sources.values())
    assert sources["correo"]["archive_urls"][0] == "https://diariocorreo.pe/salud/"
