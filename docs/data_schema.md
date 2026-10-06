# Esquema de datos vigente

Object Storage es el espacio operativo del pipeline cloud. El flujo sigue una
organización Medallion con los prefijos `bronze/`, `silver/` y `gold/`; las
tablas de revisión pueden exportarse a Google Sheets o Label Studio sin perder
los identificadores de trazabilidad.

## Bronze

Una fila representa una noticia candidata todavía no validada. Se mantienen diez campos:

| Campo | Uso |
| --- | --- |
| `record_id` | Hash estable de la URL canónica; se usa para deduplicar. |
| `source_name` | Medio o institución de procedencia. |
| `canonical_url` | URL normalizada que permite volver a la noticia original. |
| `published_at` | Fecha publicada cuando la fuente la entrega. |
| `title`, `subtitle_or_bajada` | Texto visible para decidir si la candidata merece revisión. |
| `topic` | Tema o archivo público que permitió descubrirla. |
| `selection_status` | `PENDIENTE`, `INCLUIR`, `EXCLUIR_NO_MEDICA`, `EXCLUIR_SIN_AFIRMACION` o `EXCLUIR_SIN_TEXTO`. |
| `retrieved_at` | Fecha UTC de recuperación. |
| `country` | Código ISO-2 canónico del país latinoamericano de la fuente, por ejemplo `pe` o `pr`. |

La Function elimina duplicados dentro de la corrida y vuelve a consultar los
`record_id` existentes antes de escribir el siguiente lote.

## Silver

`silver/body/` conserva el resultado técnico de extracción. `silver/claims/`
recibe únicamente cuerpos válidos y añade el claim candidato. `silver/evidence/`
guarda candidatos PubMed para los claims elegibles. Conserva la trazabilidad
anterior y añade:

| Campo | Uso |
| --- | --- |
| `record_id`, `source_name`, `topic`, `title`, `canonical_url` | Identidad y trazabilidad mínima de la noticia. |
| `body` | Texto principal descargado desde la URL pública. |
| `http_status` | Código HTTP obtenido. |
| `extraction_method` | `trafilatura`, respaldo con BeautifulSoup o ausencia de extracción. |
| `extraction_status` | `OK`, `CUERPO_INSUFICIENTE` o error de descarga. |
| `extracted_at` | Fecha UTC de extracción. |
| `claim_text` | Afirmación candidata en español. |
| `claim_text_en` | Traducción fiel usada para buscar literatura biomédica. |
| `pubmed_query_en` | Consulta PubMed en inglés generada para el claim. |
| `query_status` | `OK`, `ERROR` o `SKIPPED_NOT_ELIGIBLE`. |
| `llm_key_slot` | Slot cargado de las claves Gemini 1/2 que produjo la fila; no contiene la clave. |
| `pubmed_results_json` | Hasta diez artículos candidatos con PMID, abstract original en inglés, traducción al español, URL, similitud de OCI Embed 4 y score TF-IDF auxiliar. |
| `evidence_status` | `OK`, `NO_RESULTS`, `NO_ABSTRACT` o `ERROR`. |
| `translation_status` | `OK`, `PARTIAL`, `ERROR`, `NO_ABSTRACTS` o estado de omisión. Un candidato puede marcarse `PARAPHRASED` si Gemini bloquea la traducción literal por recitación. |
| `translation_key_slot` | Slot cargado de las claves Gemini 3/4 que produjo la traducción; no contiene la clave. |
| `best_cosine_similarity` | Similitud coseno del mejor candidato según OCI Embed 4; si OCI no está disponible, conserva el fallback TF-IDF; sirve para ordenar, no para etiquetar. |
| `best_embedding_similarity` | Mejor similitud coseno calculada con `cohere.embed-v4.0`; es un apoyo de ranking y no una etiqueta. |
| `best_tfidf_similarity` | Mejor similitud TF-IDF entre claim y abstract traducido al español; sirve como score auxiliar. |
| `embedding_status` | Estado de la llamada a OCI Embed 4 (`OK`, `ERROR`, `NO_CANDIDATES` o `SKIPPED_NO_EVIDENCE`). |
| `embedding_model`, `embedding_query_field` | Modelo usado y campo del claim enviado a Embed 4 (`claim_text_en` o `claim_text`). |
| `ranking_method` | `oci_cohere_embed_v4` cuando Embed 4 rankea los candidatos; `tfidf_v1_es` si se usa el fallback. |
| `main_medical_claim` | Afirmación médica principal delimitada manualmente. |
| `label` | `PENDIENTE`, `RESPALDADA`, `REFUTADA`, `NO_DETERMINABLE` o `EXCLUIDA`. |
| `evidence_url` | Fuente especializada usada para contrastar la afirmación. |
| `verification_note` | Explicación breve de por qué la evidencia respalda, refuta o no permite concluir. |
| `reviewer`, `validation_status` | Responsable y estado `PENDIENTE` o `COMPLETADA`. |

La extracción del cuerpo no asigna una etiqueta. Si el texto no alcanza el
mínimo, `silver/body/` conserva una fila con `CUERPO_INSUFICIENTE` para la
auditoría y no se crea una fila posterior en `silver/claims/`; Bronze puede
marcarse como `EXCLUIR_SIN_TEXTO` durante la revisión. Las decisiones médicas
y de veracidad siguen siendo humanas y basadas en evidencia.

## Gold

Es una salida generada y no debe editarse manualmente. Solo incluye noticias de `Silver` que cumplen simultáneamente:

- `validation_status=COMPLETADA`;
- etiqueta binaria `RESPALDADA` o `REFUTADA`;
- `body`, `main_medical_claim` y `evidence_url` no vacíos.

Una fila por `record_id` conserva siete campos: `record_id`, `topic`, `source_name`, `title`, `body`, `label` y `dataset_split`. Para entrenar, se concatena `title + body` como entrada y se usa `label` como objetivo. `source_name` y `topic` no son variables predictoras. `dataset_split` permanece vacío hasta aplicar la partición estratificada 70/15/15.

## Artefactos temporales

- `data/00_control/run_registry.csv`: estado y cantidades de cada ejecución local.
- `data/01_candidates/<run_id>.csv`: salida temporal del recolector local histórico.
- `reports/runs/<run_id>.json`: temas intentados, resultados por medio, duplicados y límites encontrados.

Estos archivos están ignorados por Git y no constituyen el corpus final.
