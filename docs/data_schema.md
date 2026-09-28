# Esquema de datos vigente

Google Sheets es el espacio de trabajo del corpus. El repositorio genera únicamente artefactos temporales para alimentar las pestañas `Raw` y `Extraccion`.

## Raw

Una fila representa una noticia candidata todavía no validada.

| Campo | Uso |
| --- | --- |
| `run_id` | Corrida que descubrió la candidata. |
| `record_id` | Hash estable de la URL canónica; se usa para deduplicar. |
| `source_dataset`, `source_name`, `source_domain` | Procedencia y medio. |
| `url`, `canonical_url` | URL recibida y versión normalizada sin rastreadores. |
| `published_at` | Fecha publicada cuando la fuente la entrega. |
| `title`, `subtitle_or_bajada`, `author` | Metadatos editoriales. |
| `newsdata_article_id` | Identificador de NewsData, vacío para archivos públicos. |
| `api_query` | Tema consultado o URL del archivo público. |
| `retrieved_at` | Fecha UTC de recuperación. |
| `is_medical` | `SI`, `NO` o `PENDIENTE`, decidido por revisión humana. |
| `medical_relevance_reason` | Justificación breve de inclusión o descarte. |
| `is_claim_eligible` | Indica si existe una afirmación médica concreta y verificable. |
| `review_status` | Estado de la revisión de la candidata. |

El Colab elimina duplicados dentro de la corrida y vuelve a consultar los `record_id` existentes inmediatamente antes de anexar.

## Extraccion

Solo recibe filas de `Raw` con `is_medical=SI`, `is_claim_eligible=SI` y `review_status=COMPLETADA`. Conserva la trazabilidad anterior y añade:

| Campo | Uso |
| --- | --- |
| `body` | Texto principal descargado desde la URL pública. |
| `http_status` | Código HTTP obtenido. |
| `extraction_method` | `trafilatura`, respaldo con BeautifulSoup o ausencia de extracción. |
| `extraction_status` | `OK`, `CUERPO_CORTO` o error de descarga. |
| `extracted_at` | Fecha UTC de extracción. |
| `main_medical_claim` | Afirmación médica principal delimitada manualmente. |
| `evidence_source`, `evidence_url`, `evidence_excerpt` | Evidencia usada para contrastar la afirmación. |
| `label`, `label_reason` | Etiqueta manual y su justificación. |
| `final_training_eligible` | Decisión final de inclusión en el corpus binario. |
| `reviewer`, `validation_status`, `validated_at` | Responsable y trazabilidad de validación. |

La extracción del cuerpo no asigna una etiqueta. Las decisiones médicas y de veracidad siguen siendo humanas y basadas en evidencia.

## Artefactos temporales

- `data/00_control/run_registry.csv`: estado y cantidades de cada ejecución local.
- `data/01_candidates/<run_id>.csv`: salida temporal consumida por el Colab.
- `reports/runs/<run_id>.json`: temas intentados, resultados por medio, duplicados y límites encontrados.

Estos archivos están ignorados por Git y no constituyen el corpus final.
