from pathlib import Path

from peruvian_medical_misinformation.newsdata import load_yaml, validate_batch_config


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_batch_uses_diverse_verified_textual_health_sources() -> None:
    config = load_yaml(REPOSITORY_ROOT / "configs" / "batch.yaml")
    batch, sources = validate_batch_config(config)

    assert batch["per_source_limit"] == 2
    assert batch["expected_total"] == 12
    assert batch["max_requests_per_source"] == 2
    assert batch["max_requests_total"] == 4
    assert batch["priority_query_count"] == 2
    assert list(sources) == [
        "el_comercio",
        "la_republica",
        "correo",
        "ojo",
        "minsa",
        "gestion",
        "el_popular",
        "canal_n",
    ]
    assert all(source["discovery"] == "archive" for source in sources.values())
    assert all(source.get("newsdata_fallback", False) is False for source in sources.values())
    assert sources["correo"]["archive_urls"][0] == "https://diariocorreo.pe/salud/"
    assert sources["minsa"]["source_dataset"] == "archive_minsa_institucional"
