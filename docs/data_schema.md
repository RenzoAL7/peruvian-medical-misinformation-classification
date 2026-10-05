# Esquema de datos vigente

Object Storage es el espacio operativo del pipeline cloud. El flujo sigue una
organización Medallion con los prefijos `bronze/`, `silver/` y `gold/`; las
tablas de revisión pueden exportarse a Google Sheets o Label Studio sin perder
los identificadores de trazabilidad.

## Bronze

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

## Silver

`silver/body/` conserva el resultado técnico de extracción. `silver/claims/`
recibe únicamente cuerpos válidos y añade el claim candidato. `silver/evidence/`
guarda candidatos PubMed para los claims elegibles. Conserva la trazabilidad
anterior y añade:

| Campo | Uso |
| --- | --- |
| `body` | Texto principal descargado desde la URL pública. |
| `http_status` | Código HTTP obtenido. |
| `extraction_method` | `trafilatura`, respaldo con BeautifulSoup o ausencia de extracción. |
| `extraction_status` | `OK`, `CUERPO_INSUFICIENTE` o error de descarga. |
| `extracted_at` | Fecha UTC de extracción. |
| `claim_text` | Afirmación candidata en español. |
| `claim_text_en` | Traducción fiel usada para buscar literatura biomédica. |
| `pubmed_query_en` | Consulta PubMed en inglés generada para el claim. |
| `query_status` | `OK`, `ERROR` o `SKIPPED_NOT_ELIGIBLE`. |
| `pubmed_results_json` | Hasta cinco artículos candidatos con PMID, abstract original en inglés, traducción al español, URL y similitud. |
| `evidence_status` | `OK`, `NO_RESULTS`, `NO_ABSTRACT` o `ERROR`. |
| `translation_status` | `OK`, `PARTIAL`, `ERROR`, `NO_ABSTRACTS` o estado de omisión. Un candidato puede marcarse `PARAPHRASED` si Gemini bloquea la traducción literal por recitación. |
| `best_cosine_similarity` | Mejor similitud TF-IDF entre claim y abstract traducido al español; sirve para ordenar, no para etiquetar. |
| `main_medical_claim` | Afirmación médica principal delimitada manualmente. |
| `evidence_source`, `evidence_url`, `evidence_excerpt` | Evidencia usada para contrastar la afirmación. |
| `label`, `label_reason` | Etiqueta manual y su justificación. |
| `final_training_eligible` | Decisión final de inclusión en el corpus binario. |
| `reviewer`, `validation_status`, `validated_at` | Responsable y trazabilidad de validación. |

La extracción del cuerpo no asigna una etiqueta. Las decisiones médicas y de veracidad siguen siendo humanas y basadas en evidencia.
Un cuerpo necesita al menos 150 palabras y 800 caracteres para quedar con `extraction_status=OK`; de lo contrario, el Colab fija `final_training_eligible=NO` por insuficiencia técnica.

## Gold

Es una salida generada y no debe editarse manualmente. Solo incluye noticias de `Silver` que cumplen simultáneamente:

- `extraction_status=OK`;
- `final_training_eligible=SI`;
- `validation_status=COMPLETADA`;
- etiqueta binaria `RESPALDADA` o `REFUTADA`;
- fuente, URL y extracto de evidencia no vacíos.

Una fila por `record_id` conserva los campos utilizados para auditoría y entrenamiento: procedencia, URL canónica, fecha, título, bajada, autor, cuerpo, afirmación, evidencia, etiqueta, justificación, revisor y fecha de validación. `dataset_split` permanece vacío hasta aplicar la partición estratificada 70/15/15.

## Artefactos temporales

- `data/00_control/run_registry.csv`: estado y cantidades de cada ejecución local.
- `data/01_candidates/<run_id>.csv`: salida temporal consumida por el Colab.
- `reports/runs/<run_id>.json`: temas intentados, resultados por medio, duplicados y límites encontrados.

Estos archivos están ignorados por Git y no constituyen el corpus final.
