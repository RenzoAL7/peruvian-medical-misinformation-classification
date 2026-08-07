# Scripts

Los scripts serán puntos de entrada reproducibles. Convención sugerida:

- `audit_dataset.py`
- `build_qrels.py`
- `run_tfidf_baseline.py`
- `run_sbert_baseline.py`
- `train_triplet_model.py`
- `evaluate_ranking.py`

Cada script deberá recibir una configuración de `configs/`, registrar la semilla usada y guardar sus resultados en una ruta versionada dentro de `reports/`.
