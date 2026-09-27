# Esquema de datos

## 0. Contador de corridas

data/00_control/run_registry.csv agrega una fila por cada ejecución real. Sus
campos principales son `run_number`, `run_id`, `executed_at`, `status`,
`expected_total`, `collected_total`, `shortfall_total`, `total_requests`, rutas
del CSV y del reporte. El contador aumenta aunque la API deje una corrida
parcial, para no perder trazabilidad.

## 1. Candidatas de una corrida

Cada ejecución de 01_collect_newsdata_urls.py crea data/01_candidates/<run_id>.csv. Una fila representa una candidata devuelta por NewsData.io, no una noticia ya validada.

| Campo | Descripción |
| --- | --- |
| run_id, seeded_from_run_id | Identificador de la corrida actual y, si aplica, de la corrida parcial de la que se conservó la candidata. |
| record_id | Hash corto y estable de la URL canónica. |
| source_dataset, source_id, source_name, source_domain | Procedencia configurada. |
| url, canonical_url | Enlace recibido y versión sin parámetros de seguimiento. |
| title, description, author | Metadatos de texto suministrados por la API. |
| published_at, language, country, category | Fecha y clasificación declaradas por la API. |
| newsdata_article_id, api_query, retrieved_at | Trazabilidad de la respuesta y de la consulta. |

Los valores permitidos de source_dataset son newsdata_el_comercio, newsdata_rpp, newsdata_latina, newsdata_el_peruano, newsdata_peru21 y newsdata_la_republica.

## 2. Revisión humana

02_create_manual_review.py crea data/02_review/<run_id>_manual_review.csv. Conserva los campos de procedencia y añade los siguientes campos editables.

| Campo | Regla de uso |
| --- | --- |
| is_medical | SI cuando el investigador confirma que el caso trata una afirmación de salud/medicina; NO en caso contrario. |
| medical_relevance_reason | Breve razón de inclusión o descarte temático. |
| body | Cuerpo de la noticia obtenido y pegado por el investigador. |
| main_medical_claim | Una afirmación médica verificable delimitada manualmente. |
| evidence_source, evidence_url, evidence_excerpt | Fuente, enlace y fragmento que respaldan el contraste. |
| label | 0, 1 o EXCLUIDA; nunca se llena a partir del medio. |
| label_reason | Razón concisa que conecta afirmación y evidencia. |
| reviewer, review_status, reviewed_at | Responsable, estado y fecha de la revisión. |

La hoja se debe conservar como CSV UTF-8. La revisión final debe usar review_status=COMPLETADA.

## 3. Corpus binario real

03_export_training_csv.py filtra el CSV manual y crea data/03_processed/training_corpus_real.csv con las columnas siguientes:

| Campo | Descripción |
| --- | --- |
| record_id | Identificador de la candidata original. |
| text | Concatenación normalizada de título, bajada y cuerpo. |
| label | Solo 0 o 1. |
| source_dataset, source_name, url, published_at | Metadatos para auditoría, no variables del modelo. |
| is_synthetic | false en esta fase. |

Una fila SI solo entra al corpus final si tiene cuerpo, afirmación principal, fuente y URL de evidencia, razón de etiqueta, estado COMPLETADA y etiqueta binaria. Se eliminan duplicados exactos por URL canónica o texto normalizado al exportar. Las filas NO y EXCLUIDA permanecen en la hoja de revisión, pero no ingresan al CSV de entrenamiento.
