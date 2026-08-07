# Notebooks

Usar nombres numerados y un propósito único por notebook:

1. `01_dataset_audit.ipynb`: perfiles de columnas, nulos, duplicados y distribución.
2. `02_qrels_exploration.ipynb`: revisión del ground truth y particiones.
3. `03_tfidf_baseline.ipynb`: baseline léxico y métricas de ranking.
4. `04_sbert_baseline.ipynb`: baseline semántico.
5. `05_triplet_experiment.ipynb`: ajuste y comparación final.

Cuando un flujo se estabilice, migrarlo a `src/` y `scripts/` para que sea reproducible sin depender del notebook.
