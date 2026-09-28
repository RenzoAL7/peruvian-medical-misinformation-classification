from __future__ import annotations

import subprocess
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_repository_does_not_track_csv_data() -> None:
    result = subprocess.run(
        ["git", "ls-files", "*.csv"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == ""


def test_obsolete_local_review_pipeline_is_not_present() -> None:
    obsolete_paths = [
        "scripts/00_show_run_history.py",
        "scripts/02_create_manual_review.py",
        "scripts/03_export_training_csv.py",
        "src/peruvian_medical_misinformation/review.py",
        "data/02_review",
        "data/03_processed",
    ]

    assert all(not (REPOSITORY_ROOT / path).exists() for path in obsolete_paths)
