# Organización de datos

Las carpetas siguen el orden real del proceso. Los resultados de pruebas y corridas personales se conservan localmente; el batch compartido oficial del equipo se versiona para que ambos investigadores partan de las mismas URLs y la misma hoja de revisión.

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

El contador registra tanto corridas completas como parciales. Una corrida parcial no se borra: permite reanudar la búsqueda sin perder las URLs ya obtenidas.

## Batch compartido 001

El punto de partida compartido es la corrida completa `run_004_20260927T143557Z`:

- `01_candidates/run_004_20260927T143557Z.csv`: 12 candidatas, dos por cada una de las seis fuentes.
- `02_review/run_004_20260927T143557Z_manual_review.csv`: plantilla que ambos investigadores editarán para decidir pertinencia médica, elegibilidad de la afirmación, evidencia y etiqueta.

No creen una segunda hoja para este batch. Coordinen la edición de esa misma plantilla y registren el revisor en la columna `reviewer`. Las corridas anteriores parciales y los archivos futuros que no se designen como compartidos continúan ignorados por Git.

No se usa Parquet. Las etiquetas son 0 (compatible con evidencia), 1 (contradicha por evidencia) y EXCLUIDA (no verificable, ambigua o no separable). EXCLUIDA y las noticias no médicas no ingresan al CSV binario final.
