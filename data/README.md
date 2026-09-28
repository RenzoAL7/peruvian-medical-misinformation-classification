# Organización de datos

Las carpetas siguen el orden real del proceso. Todos los CSV son artefactos locales o temporales: el repositorio conserva código, configuración, documentación y pruebas, pero no versiona candidatas, revisiones humanas ni corpus procesados.

    data/
    ├── 00_control/
    │   └── run_registry.csv
    │       Historial: número, identificador, estado y cantidad obtenida por corrida.
    ├── 01_candidates/
    │   └── <run_id>.csv
    │       URLs y metadatos devueltos por NewsData.io.
    ├── 02_review/
    │   └── <run_id>_manual_review.csv
    │       Hoja que el investigador completa en Excel.
    └── 03_processed/
        └── training_corpus_real.csv
        Corpus binario real generado después de la revisión.

El contador registra tanto corridas completas como parciales. Una corrida parcial no se borra localmente: permite reanudar la búsqueda sin perder las URLs ya obtenidas. La hoja compartida en Google Drive es la fuente de trabajo del equipo y no se copia al historial de Git.

No se usa Parquet. Las etiquetas son 0 (compatible con evidencia), 1 (contradicha por evidencia) y EXCLUIDA (no verificable, ambigua o no separable). EXCLUIDA y las noticias no médicas no ingresan al CSV binario final.
