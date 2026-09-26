# Esquema de datos del corpus médico peruano

## Principio de trazabilidad

Cada fila conserva su origen, el estado de extracción y la relación con un
posible duplicado. El texto que eventualmente recibe un modelo será
`title + subtitle_or_bajada + body`; URL, fuente, fecha y autor siguen siendo
solo metadatos.

## Corpus consolidado

| Campo | Descripción |
| --- | --- |
| `record_id` | Identificador estable derivado de la URL canónica. |
| `source_dataset` | `scraped_rpp`, `scraped_el_comercio` o `scraped_latina`. |
| `source_name` | Medio o fuente original. |
| `url`, `canonical_url` | URL recibida y URL sin parámetros de seguimiento. |
| `retrieved_at`, `published_at` | Recuperación UTC y fecha de publicación normalizada cuando existe. |
| `title`, `subtitle_or_bajada`, `body` | Texto extraído, sin usarlo para etiquetar automáticamente. |
| `author`, `section`, `language` | Metadatos de autoría, sección e idioma detectado. |
| `http_status` | Código HTTP observado durante la descarga. |
| `scraping_method` | `trafilatura` o `beautifulsoup_fallback`. |
| `raw_html_path` | Ruta local a una versión de la captura HTML original. |
| `content_hash`, `normalized_content_hash` | SHA-256 del texto original y normalizado. |
| `normalized_text` | Texto NFKC con espacios normalizados y tildes/negaciones conservadas. |
| `extraction_status` | `valid`, `needs_review`, `excluded` o `error`. |
| `exclusion_reason` | Motivo verificable de exclusión, revisión o error. |
| `duplicate_status` | `unique`, `exact_url`, `exact_content` o `near_duplicate`. |
| `duplicate_of_record_id`, `duplicate_similarity` | Registro de referencia y similitud cuando corresponde. |
| `run_id` | Identificador de la corrida de descubrimiento o extracción. |

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

## Vista CSV con columnas del profesor

`data/processed/medical_news_professor_style_2026.csv` es una vista derivada
para trabajar en una hoja simple. Tiene una fila por noticia y estas columnas:

| Columna | Origen o regla |
| --- | --- |
| `ID` | `record_id` del corpus trazable. |
| `CATEGORY` | Vacío hasta la revisión humana; nunca se infiere desde la fuente. |
| `TOPICS` | `Salud`. |
| `SOURCE`, `Tipo de Fuente` | Medio de origen y `Medio de comunicación`. |
| `HEADLINE` | Título extraído. |
| `TEXT` | Bajada y cuerpo, conservando saltos de párrafo. |
| `LINK`, `Certificado de seguridad` | URL original y `Sí` cuando usa HTTPS. |
| `Fecha`, `Hora`, `Autor` | Fecha/hora de publicación y autor cuando se extrajeron. |

El CSV trazable sigue siendo la fuente de verdad para URL canónica, HTML,
hashes, estado de extracción, duplicados y revisión de evidencia.

## Resumen de la corrida

`reports/collection_summary.json` informa los conteos por `source_dataset`, los
registros válidos únicos, estados de duplicación, errores, exclusiones y la
cantidad de valores faltantes por campo trazable. Así las ausencias causadas por
una extracción se registran sin inventar valores.
