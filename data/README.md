# Organización de datos

El corpus reúne noticias médicas en español de El Comercio, RPP Noticias y
Latina Noticias. El archivo compartido para la tesis es:

```text
data/processed/medical_news_corpus_2026.csv
```

Contiene 154 registros con título, bajada, cuerpo, URL, fecha, fuente, estado
de extracción, hashes, rutas de HTML y campos vacíos para revisión humana. Se
versiona únicamente en este repositorio privado del equipo. No existe una
versión Parquet.

```text
data/
├── raw/          # HTML original y manifiestos locales; ignorados por Git
├── interim/      # JSONL y logs de extracción; ignorados por Git
├── annotations/  # copias de trabajo para revisión humana; ignoradas por Git
└── processed/    # corpus CSV privado y, luego, dataset binario etiquetado
```

Las etiquetas finales serán `0` (no desinformación) o `1` (desinformación).
`EXCLUIDA` se utiliza en la revisión para afirmaciones ambiguas, contradictorias
o no verificables, y no entra al conjunto de entrenamiento. La fuente no decide
la etiqueta.

El texto de entrada previsto es `title + subtitle_or_bajada + body`. Las URLs,
fuentes, fechas, evidencia y notas de revisión son metadatos de trazabilidad,
no características del modelo. No se entrena hasta completar la revisión humana
y la deduplicación.
