from pathlib import Path

from peruvian_medical_misinformation.newsdata import load_yaml, validate_batch_config


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_batch_12_keeps_the_six_approved_outlets_and_discovery_modes() -> None:
    config = load_yaml(REPOSITORY_ROOT / "configs" / "batch_12.yaml")
    batch, sources = validate_batch_config(config)

    assert batch["per_source_limit"] == 2
    assert batch["expected_total"] == 12
    assert list(sources) == [
        "el_comercio",
        "rpp",
        "latina",
        "el_peruano",
        "peru21",
        "la_republica",
    ]
    assert {
        source_id: source.get("discovery", "newsdata")
        for source_id, source in sources.items()
    } == {
        "el_comercio": "newsdata",
        "rpp": "newsdata",
        "latina": "archive",
        "el_peruano": "newsdata",
        "peru21": "archive",
        "la_republica": "newsdata",
    }
    assert sources["latina"]["newsdata_fallback"] is True
    assert sources["peru21"]["newsdata_fallback"] is True

