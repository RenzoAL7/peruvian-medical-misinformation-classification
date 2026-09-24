# Metodología de Seminario 1

## 1. Objetivo y alcance

El estudio construye y evalúa modelos para clasificar noticias médicas en
español relacionadas con Perú. La tarea es estrictamente binaria:

```text
REAL: la afirmación médica central está respaldada por evidencia confiable.
FAKE: la afirmación médica central es contradicha directamente por evidencia confiable.
```

No se implementan categorías temáticas, clasificación multiclase, ranking de
fuentes, RAG, generación de respuestas, Triplet Loss ni recomendaciones de
documentos. Esos componentes no forman parte de Seminario 1.

## 2. Unidad de análisis y fuentes

La unidad de análisis es una noticia o publicación informativa que contiene una
afirmación médica central verificable. La primera versión del corpus utilizará
El Comercio, RPP Noticias y Latina Noticias como fuentes periodísticas peruanas
aprobadas.

El nombre del medio, la URL y la fecha son metadatos de procedencia. No son
categorías del modelo y no determinan por sí solos la etiqueta. Una noticia
publicada por un medio confiable no se marca automáticamente como `REAL`, y
una noticia de un medio distinto no se marca automáticamente como `FAKE`.

## 3. Proceso de obtención del dataset

### 3.1 Registro de fuentes

Cada fuente se registra en `configs/sources.yaml` con un identificador, nombre,
dominios permitidos y modalidad de adquisición. La extracción comienza con un
manifiesto local de URLs (`data/raw/source_urls.csv`). Esto permite repetir la
misma colección y revisar qué páginas fueron incluidas.

No se rastrean dominios completos ni se evaden controles de acceso. Se usan
URLs obtenidas mediante búsqueda dirigida, RSS, APIs públicas o selección
manual, respetando términos de uso, robots.txt, límites de consulta y derechos
de reproducción.

### 3.2 Extracción dirigida

`scripts/01_collect_sources.py` valida que cada URL use HTTP(S) y pertenezca al
dominio autorizado. Para cada página registra:

- URL original y URL canónica cuando está disponible;
- identificador estable derivado de la URL;
- fuente y dominio;
- fecha de descarga;
- título y fecha de publicación detectados;
- texto extraído;
- método y estado de extracción;
- código HTTP o mensaje de error.

El resultado es un JSONL local. No se guarda HTML innecesario en el repositorio
ni se versionan los textos descargados.

### 3.3 Limpieza y control inicial

Se eliminan elementos de navegación, scripts, publicidad y espacios repetidos.
Se conservan el registro original y la versión limpia para poder auditar la
transformación. Los registros sin texto suficiente pasan a revisión y no se
incluyen automáticamente en el dataset final.

Se eliminan duplicados por URL canónica y se revisan duplicados de contenido,
noticias sindicadas y copias con cambios mínimos. El proceso no inventa texto
cuando una página no puede extraerse: registra el fallo y conserva la URL para
revisión manual.

## 4. Anotación binaria

### 4.1 Afirmación central

Para cada noticia elegible se redacta o delimita una sola afirmación médica
central. Si una noticia contiene varias afirmaciones que no pueden separarse sin
cambiar su sentido, se excluye del conjunto final.

### 4.2 Evidencia

La afirmación se contrasta con PubMed y, cuando corresponde, con MINSA, INS,
EsSalud, OMS/OPS, guías clínicas, revisiones sistemáticas, metaanálisis o
consensos profesionales. Se registra la consulta, fecha, PMID o URL, tipo de
fuente y una justificación breve.

La evidencia respalda la decisión humana, pero no se entrega como característica
al modelo. El modelo recibe el texto de la noticia y la etiqueta, no palabras
como “falso”, el veredicto de un fact-checker ni la justificación de la
anotación.

### 4.3 Regla de etiqueta

- `REAL`: la afirmación central está respaldada por la evidencia seleccionada.
- `FAKE`: la evidencia seleccionada contradice directamente la afirmación.

Los casos ambiguos, no verificables, sin evidencia suficiente o con afirmaciones
múltiples se excluyen del dataset final. No se convierten en una tercera clase.

El piloto de 200 registros permite revisar la claridad de estas reglas antes de
escalar hacia un corpus aproximado de 1,000 registros, idealmente balanceado
entre ambas etiquetas.

## 5. Esquema de datos

La hoja de anotación conserva la procedencia y la decisión:

```text
record_id
url
canonical_url
source_name
published_at
retrieved_at
title
text
claim_text
label
evidence_url
evidence_type
pmid
pubmed_query
query_date
verdict_reason
annotator_1
annotator_2
adjudication
notes
```

La variable usada para el entrenamiento es `label`, con valores únicamente
`REAL` y `FAKE`. `source_name`, `evidence_url` y las demás columnas de auditoría
no son clases ni deben incorporarse como características sin una justificación
experimental explícita.

## 6. Preparación para el entrenamiento

Antes del split se eliminan duplicados, conflictos de etiqueta y registros sin
texto. El texto de entrada se define de forma fija, por ejemplo como título más
cuerpo limpio. Las particiones de entrenamiento, validación y prueba se
realizan de forma estratificada y evitando que la misma URL, copia o evento
noticioso aparezca en particiones distintas.

La evidencia y la decisión de los anotadores se conservan para auditoría, pero
no se usan para crear una predicción privilegiada. Así se evita la fuga de
información hacia el modelo.

## 7. Modelos y evaluación

Se comparan representaciones y clasificadores binarios:

- TF-IDF con regresión logística, SVM y Naive Bayes;
- embeddings de palabras con modelos recurrentes;
- sentence transformers con un clasificador binario;
- transformers en español con una cabeza de clasificación.

La métrica principal es Macro-F1. También se reportan precision, recall,
ROC-AUC, matriz de confusión y análisis descriptivo de errores.

## 8. Reproducibilidad y límites

Cada ejecución debe conservar la versión del manifiesto, fecha de extracción,
configuración, estado HTTP, versión del código y conteos antes y después de
cada filtro. Las claves de API y los textos que no puedan redistribuirse no se
suben a Git.

Scopus se mantiene fuera de la construcción del dataset: se usa para buscar y
documentar papers. PubMed y las fuentes sanitarias se usan para justificar las
etiquetas. El resultado de Seminario 1 es un clasificador binario reproducible,
no un sistema de recomendación ni un verificador automático autónomo.
