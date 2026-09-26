# Clasificación binaria de desinformación médica peruana

Repositorio de Seminario 1 para construir y evaluar un clasificador binario de
noticias médicas en español relacionadas con Perú.

La unidad de predicción será el texto de la noticia. Tras la revisión humana,
la variable objetivo será:

```text
0 = no desinformación | 1 = desinformación
```

El corpus se recopila inicialmente desde El Comercio, RPP Noticias y Latina
Noticias. La evidencia científica se usa para justificar la etiqueta, no como
una tercera clase ni como entrada del modelo.

## Alcance de Seminario 1

El flujo del repositorio es:

```text
URLs de fuentes permitidas
  → extracción dirigida de noticias
  → preservación de metadatos y procedencia
  → limpieza y deduplicación
  → identificación de la afirmación médica central
  → verificación de la afirmación
  → etiquetas 0/1
  → división train/validation/test
  → entrenamiento y comparación de clasificadores
```

Los casos ambiguos, sin evidencia suficiente o imposibles de separar no se
convierten en una tercera etiqueta: se excluyen del dataset final y se dejan
registrados en la auditoría.

Scopus se utiliza únicamente para localizar papers y documentar el estado del
arte. PubMed y las fuentes sanitarias oficiales se utilizan como evidencia para
la anotación. Ninguna de esas fuentes reemplaza el texto de la noticia que
recibirá el clasificador.

## Recolección reproducible

La recolección no rastrea indiscriminadamente dominios completos. Se trabaja
con un manifiesto de URLs revisadas y una lista de dominios permitidos:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[scraping]'

.venv/bin/python scripts/01_collect_sources.py \
  --config configs/sources.yaml \
  --urls-file data/raw/source_urls_candidates_pending_period.csv \
  --output data/interim/scraped_news.jsonl \
  --raw-html-dir data/raw/html \
  --log data/interim/extraction_log.csv

.venv/bin/python scripts/01a_enrich_local_metadata.py \
  --input data/interim/scraped_news.jsonl \
  --output data/interim/scraped_news_enriched.jsonl \
  --log data/interim/extraction_log.csv

.venv/bin/python scripts/01b_consolidate_corpus.py \
  --input data/interim/scraped_news_enriched.jsonl \
  --output data/processed/medical_news_corpus_2026.csv \
  --start-date 2026-01-01 \
  --end-date 2026-09-26
```

El manifiesto local debe contener al menos `url` y `source_id`. Cada respuesta
HTML se conserva localmente con un nombre versionado; el JSONL conserva la
captura de extracción y el CSV consolida `title`, `subtitle_or_bajada`, `body`,
metadatos, estados y la plantilla de revisión humana. Ninguno de estos datos se
genera como Parquet. El HTML original, JSONL y log permanecen locales e
ignorados por Git. El corpus consolidado se versiona únicamente en este
repositorio privado para el trabajo de los dos tesistas. Antes de recolectar se
deben revisar los términos de uso, robots.txt, límites de consulta y permisos
de cada fuente.

El CSV consolidado ya contiene los campos de anotación. Las etiquetas permanecen
vacías hasta la revisión humana; `EXCLUIDA` solo se usa para casos no
verificables, ambiguos, contradictorios o insuficientes. No se debe entrenar con
este CSV hasta completar ese protocolo.

La plantilla separada puede generarse si se necesita una copia de trabajo:

```bash
.venv/bin/python scripts/02_prepare_annotation.py \
  --input data/interim/scraped_news.jsonl \
  --output data/annotations/annotation_template.csv
```

Una vez completadas manualmente las etiquetas y la evidencia:

```bash
.venv/bin/python scripts/03_build_binary_dataset.py \
  --input data/annotations/annotation_template.csv \
  --output data/processed/medical_misinformation_binary.csv
```

## Estructura

```text
.
├── configs/
│   ├── base.yaml                 # alcance, datos, splits y evaluación
│   └── sources.yaml              # fuentes y dominios permitidos
├── data/
│   ├── raw/                      # URLs y capturas locales, no versionado
│   ├── annotations/              # anotación y evidencia, no versionado
│   ├── interim/                  # transformaciones temporales
│   ├── processed/                # corpus CSV privado y dataset binario final
│   └── source_urls.example.csv   # plantilla versionada
├── docs/methodology.md           # protocolo metodológico
├── scripts/
│   ├── 01_collect_sources.py     # extracción dirigida y almacenamiento local
│   ├── 01a_enrich_local_metadata.py # recupera metadatos desde HTML local
│   ├── 01b_consolidate_corpus.py # CSV trazable y plantilla de revisión
│   ├── 02_prepare_annotation.py  # plantilla de anotación
│   └── 03_build_binary_dataset.py
├── src/peruvian_medical_misinformation/
│   └── collection.py             # descarga y extracción de texto
└── tests/
```

## Modelo y evaluación

La comparación prevista es binaria y usa Macro-F1 como métrica principal,
acompañada de precision, recall, ROC-AUC y matriz de confusión. Las familias de
modelos se mantienen como experimentos posteriores de Seminario 1: TF-IDF con
Naive Bayes, regresión logística y SVM lineal; GloVe + BiLSTM; Word2Vec + LSTM;
y BERT, BETO y RoBERTa-BNE con cabeza binaria. No se entrenan en esta etapa ni
se incluyen ranking, qrels, Triplet Loss, RAG, generación de respuestas o
clasificación multiclase.

El piloto inicial será de 200 registros para comprobar las reglas de anotación.
La meta del corpus final es aproximadamente 1,000 registros válidos y
balanceados entre `0` y `1`.

## Datos y credenciales

Nunca se suben claves de Scopus ni respuestas completas de APIs. El corpus CSV
consolidado se mantiene en este repositorio privado, solo para los tesistas;
las capturas HTML y artefactos intermedios siguen fuera de Git. Se conserva la
procedencia mediante URL, fuente, fecha, estado de extracción y referencias de
evidencia. El acceso y uso de los artículos debe respetar los permisos de cada
fuente.
