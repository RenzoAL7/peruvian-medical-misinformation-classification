import csv
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_script(script: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT / "src")
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script), *arguments],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )


def test_binary_builder_outputs_only_human_reviewed_binary_rows(tmp_path):
    input_path = tmp_path / "annotations.csv"
    output_path = tmp_path / "processed.csv"
    fields = ["record_id", "title", "subtitle_or_bajada", "body", "label", "source_name"]
    with input_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerow({"record_id": "r1", "title": "Título 1", "subtitle_or_bajada": "Bajada 1", "body": "Texto 1", "label": "0"})
        writer.writerow({"record_id": "r2", "title": "Título 2", "body": "Texto 2", "label": "1"})
        writer.writerow({"record_id": "r3", "title": "Excluida", "body": "Texto 3", "label": "EXCLUIDA"})
        writer.writerow({"record_id": "r4", "title": "Sin etiqueta", "body": "Texto 4", "label": ""})

    result = run_script(
        "03_build_binary_dataset.py",
        "--input",
        str(input_path),
        "--output",
        str(output_path),
    )

    assert result.returncode == 0, result.stderr
    with output_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert [row["label"] for row in rows] == ["0", "1"]
    assert rows[0]["text"] == "Título 1\n\nBajada 1\n\nTexto 1"


def test_binary_builder_rejects_a_third_label(tmp_path):
    input_path = tmp_path / "annotations.csv"
    output_path = tmp_path / "processed.csv"
    input_path.write_text(
        "record_id,title,body,label\nr1,Título,Texto,PENDIENTE\n",
        encoding="utf-8",
    )

    result = run_script(
        "03_build_binary_dataset.py",
        "--input",
        str(input_path),
        "--output",
        str(output_path),
    )

    assert result.returncode != 0
    assert "solo acepta 0 o 1" in result.stderr
