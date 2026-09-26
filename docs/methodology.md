# Metodología de fase 1: corpus médico peruano

## 1. Objetivo y alcance

Esta entrega construye un corpus trazable de noticias médicas en español
relacionadas con Perú. El entrenamiento y la comparación de modelos ocurren
después de la adquisición, deduplicación y revisión humana.

La decisión humana futura usa tres estados de anotación:

```text
0: la afirmación médica central es compatible con evidencia confiable.
1: la afirmación médica central es contradicha por evidencia confiable.
EXCLUIDA: la afirmación es ambigua, no verificable, contradictoria o no separable.
```

El valor `EXCLUIDA` se preserva para auditoría, pero no entra en una posterior
tarea binaria. La fase 1 no implementa ranking, qrels, RAG, generación ni el
entrenamiento de clasificadores.

## 2. Unidad de análisis y fuentes

La unidad de análisis es una noticia o publicación informativa que contiene una
afirmación médica central verificable. El corpus integra dos componentes:

1. Las filas `TOPICS=Salud` del archivo entregado por el profesor, conservadas
   como `edwin_157` y con `CATEGORY` en `source_original_label`.
2. Noticias públicas de El Comercio, RPP Noticias y Latina, recolectadas como
   `scraped_el_comercio`, `scraped_rpp` y `scraped_latina`.

El nombre del medio, la URL y la fecha son metadatos de procedencia. No son
categorías del modelo y no determinan por sí solos la etiqueta. Una noticia
publicada por un medio confiable no se marca automáticamente como `0`, y una
noticia de un medio distinto no se marca automáticamente como `1`. La etiqueta
histórica `REAL/FAKE`, `VERDADERO/FALSO` o similar tampoco se convierte de forma
automática: se revisa su significado o se vuelve a verificar.

`edwin_157` es un identificador de procedencia solicitado, no una garantía de
que cualquier archivo recibido tenga exactamente 157 filas de Salud. Cada
importación informa su conteo y conserva `source_row_id`; una discrepancia debe
aclararse con quien entregó la base antes de equiparar etiquetas o publicar
estadísticas finales.

## 3. Proceso de obtención del dataset

### 3.1 Registro de fuentes

Cada fuente se registra en `configs/sources.yaml` con identificador, dominio,
`source_dataset`, rutas públicas y evidencia de revisión de `robots.txt` y
términos. `configs/base.yaml` registra un período común obligatorio antes de
iniciar Scrapy. Si falta el período, el script falla sin realizar peticiones.

No se rastrean dominios completos ni se evaden controles de acceso. Las URLs se
descubren solo desde categorías, RSS, sitemaps, archivos o buscadores internos
públicos configurados; no se extraen resultados de Google u otros buscadores.

### 3.2 Extracción dirigida

`scripts/01_discover_urls.py` crea un manifiesto reproducible. Luego
`scripts/02_collect_articles.py` usa Scrapy para validar el dominio permitido,
respetar `robots.txt`, pausar solicitudes, limitar reintentos y almacenar caché.
Para cada página registra:

- URL original y URL canónica cuando está disponible;
- identificador estable derivado de la URL;
- `source_dataset`, fuente y dominio;
- fecha de descarga;
- título y fecha de publicación detectados;
- título, bajada, cuerpo, autor y sección extraídos;
- HTML original versionado, hashes de texto y texto normalizado;
- método, estado y razón de extracción;
- código HTTP o mensaje de error.

El resultado es `data/interim/scraped_news.jsonl`, metadatos por corrida,
`extraction_log.csv` y HTML fuera de Git. La captura anterior nunca se
sobrescribe si una página se vuelve a procesar.

### 3.3 Limpieza y control inicial

Trafilatura elimina el contenido de navegación y BeautifulSoup solo actúa como
respaldo. El texto se normaliza con Unicode NFKC y espacios consistentes, sin
eliminar tildes ni negaciones como `no`, `sin` o `nunca`. Los registros vacíos,
demasiado cortos o con idioma no confirmado se excluyen o pasan a revisión.

Se marcan duplicados por URL canónica, hash exacto y similitud alta de tokens;
la fila original permanece con `duplicate_status`,
`duplicate_of_record_id` y `duplicate_similarity`. El proceso no inventa texto
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

- `0`: la afirmación central es compatible con la evidencia seleccionada.
- `1`: la evidencia seleccionada contradice directamente la afirmación.
- `EXCLUIDA`: no existe evidencia suficiente, la afirmación es ambigua o las
  afirmaciones no se pueden separar sin alterar el sentido de la noticia.

Los casos `EXCLUIDA` quedan documentados y no entran en el posterior dataset
binario. Dos revisores registran la decisión cuando sea posible y resuelven la
discrepancia mediante consenso; ningún modelo de lenguaje etiqueta por sí solo.

El mínimo de 200 registros válidos y no duplicados permite revisar la claridad
de estas reglas antes de definir cualquier ampliación posterior del corpus.

## 5. Esquema de datos

El corpus consolidado conserva URL, URL canónica, fechas, título, bajada, cuerpo,
autor, sección, HTML original, hashes, idioma, método, estado de extracción y
estado de duplicado. El diccionario completo está en `docs/data_schema.md`.

La plantilla añade `main_medical_claim`, las fuentes e identificadores de
evidencia, dos revisores, estado de revisión, desacuerdo, razón y fecha. La
variable futura `label` solo acepta `0` o `1` para entrenamiento; `EXCLUIDA`
permanece fuera del conjunto binario. `source_name`, `evidence_url` y las demás
columnas de auditoría no deben incorporarse como características.

## 6. Preparación para el entrenamiento

Antes del split se marcan duplicados, conflictos de etiqueta y registros sin
texto; las filas originales se conservan para auditoría. El texto de entrada se
define de forma fija como título + bajada + cuerpo normalizado. Las particiones
de entrenamiento, validación y prueba (70/15/15) se harán de forma estratificada
y evitando que la misma URL, copia o evento aparezca en particiones distintas.

La evidencia y la decisión de los anotadores se conservan para auditoría, pero
no se usan para crear una predicción privilegiada. Así se evita la fuga de
información hacia el modelo.

## 7. Modelos y evaluación

Se comparan representaciones y clasificadores binarios:

- TF-IDF con Naive Bayes, regresión logística y SVM lineal;
- GloVe + BiLSTM y Word2Vec + LSTM;
- BERT, BETO y RoBERTa-BNE, cada uno con una capa binaria.

La métrica principal es Macro-F1. También se reportan precision, recall,
ROC-AUC, matriz de confusión y análisis descriptivo de errores.

## 8. Relación con trabajos previos

La documentación final debe contrastar las copias disponibles de los artículos
antes de atribuirles resultados concretos. La relación de diseño solicitada es:

- Pande et al. (2022): respalda conectar adquisición automática de noticias con
  clasificación textual, sin que la recolección decida la veracidad.
- Bonet-Jover et al. (2023): respalda el procedimiento Human-in-the-Loop y la
  resolución de discrepancias entre revisores.
- Noor et al. (2025) y Obunadike et al. (2025): motivan la limpieza y
  normalización conservando señales médicas relevantes, incluidas negaciones.
- Blanco-Fernández et al. (2024): motiva conservar fuente, URL y duplicados
  para medir posteriormente la generalización entre fuentes reales.
- Nina et al. (2025): justifica comparar representaciones tradicionales, redes
  neuronales y Transformers en una fase posterior, no en esta entrega.
- Alghamdi et al. (2023): motiva evaluar arquitecturas profundas en el dominio
  sanitario después de completar el corpus anotado.

Estas relaciones son requisitos metodológicos del proyecto; las citas
bibliográficas, resultados y conclusiones de cada artículo se añadirán solo
después de verificar los archivos fuente correspondientes.

## 9. Reproducibilidad y límites

Cada ejecución debe conservar la versión del manifiesto, fecha de extracción,
configuración, estado HTTP, versión del código y conteos antes y después de
cada filtro. Las claves de API y los textos que no puedan redistribuirse no se
suben a Git.

Scopus se mantiene fuera de la construcción del dataset: se usa para buscar y
documentar papers. PubMed y las fuentes sanitarias se usan para justificar las
etiquetas. El resultado de esta fase es un corpus reproducible listo para
revisión humana, no un sistema de recomendación ni un verificador automático.
