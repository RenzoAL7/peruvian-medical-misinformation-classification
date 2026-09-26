# Esquema de datos del corpus médico peruano

## Principio de trazabilidad

Cada fila conserva su origen, el estado de extracción y la relación con un
posible duplicado. El texto que eventualmente recibe un modelo será
`title + subtitle_or_bajada + body`; URL, fuente, fecha y autor siguen siendo
solo metadatos.

## Corpus consolidado

| Campo | Descripción |
| --- | --- |
| `record_id` | Identificador estable derivado de URL canónica o fila fuente. |
| `source_dataset` | `edwin_157`, `scraped_rpp`, `scraped_el_comercio` o `scraped_latina`. |
| `source_name` | Medio o fuente original. |
| `url`, `canonical_url` | URL recibida y URL sin parámetros de seguimiento. |
| `retrieved_at`, `published_at` | Recuperación UTC y fecha de publicación normalizada cuando existe. |
| `title`, `subtitle_or_bajada`, `body` | Texto extraído, sin usarlo para etiquetar automáticamente. |
| `author`, `section`, `language` | Metadatos de autoría, sección e idioma detectado. |
| `http_status` | Código HTTP observado durante la descarga. |
| `scraping_method` | `trafilatura`, `beautifulsoup_fallback` o `provided_dataset`. |
| `raw_html_path` | Ruta local a una versión de la captura HTML original. |
| `content_hash`, `normalized_content_hash` | SHA-256 del texto original y normalizado. |
| `normalized_text` | Texto NFKC con espacios normalizados y tildes/negaciones conservadas. |
| `extraction_status` | `valid`, `needs_review`, `excluded` o `error`. |
| `exclusion_reason` | Motivo verificable de exclusión, revisión o error. |
| `duplicate_status` | `unique`, `exact_url`, `exact_content` o `near_duplicate`. |
| `duplicate_of_record_id`, `duplicate_similarity` | Registro de referencia y similitud cuando corresponde. |
| `source_original_label` | Etiqueta heredada; no equivale por sí sola a una etiqueta médica nueva. |
| `source_row_id`, `run_id` | Fila de origen y corrida reproducible. |

## Plantilla de anotación Human-in-the-Loop

Además de los campos del corpus, contiene:

| Campo | Uso |
| --- | --- |
| `main_medical_claim` | Afirmación médica principal delimitada por el revisor. |
| `evidence_source`, `evidence_url`, `evidence_identifier`, `evidence_excerpt` | Evidencia usada para revisar la afirmación. |
| `label` | `0`, `1` o `EXCLUIDA`; queda vacío hasta la revisión humana. |
| `label_reason` | Razón breve y auditable de la decisión. |
| `reviewer_1`, `reviewer_2`, `review_status` | Doble revisión y estado del caso. |
| `disagreement` | Desacuerdo y resolución por consenso. |
| `reviewed_at` | Fecha de revisión. |

Los registros duplicados o no válidos se preservan en el corpus y no pasan por
defecto a la plantilla de anotación.

## Resumen de la corrida

`reports/collection_summary.json` informa los conteos por `source_dataset`, los
registros válidos únicos, estados de duplicación, errores, exclusiones y la
cantidad de valores faltantes por campo trazable. Así las ausencias de metadatos
del dataset entregado y las ausencias causadas por una extracción se distinguen
sin inventar valores.

También preserva los conteos de `source_original_label` sin convertirlos a
`0` o `1`, junto con el estado `unmapped_pending_human_evidence_review`. Esto
evita asumir que una etiqueta histórica tiene el mismo significado que el
protocolo médico del proyecto.
