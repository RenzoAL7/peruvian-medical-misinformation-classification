# Datos locales del corpus

El repositorio conserva la estructura, los scripts y la documentación. Los resultados de cada corrida se almacenan localmente y se ignoran por Git. No se usa Parquet en esta entrega.

    data/
    ├── raw/
    │   └── source_url_runs/       # una candidata por URL/título de cada corrida
    ├── review/                    # CSV que se completa manualmente en Excel
    └── processed/                 # CSV binario real tras la revisión

El primer CSV se genera con NewsData.io y contiene metadatos de descubrimiento; no contiene cuerpos verificados ni etiquetas. La plantilla de review añade is_medical, body, afirmación médica, evidencia, etiqueta y estado de revisión. processed/training_corpus_real.csv se crea solo cuando las filas cumplen los controles de revisión manual.

Las etiquetas son 0 (compatible con la evidencia), 1 (contradicha por la evidencia) y EXCLUIDA (no verificable, ambigua o no separable). EXCLUIDA no entra al CSV binario final. El medio, URL y fecha nunca determinan la etiqueta.
