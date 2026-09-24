# Clasificación binaria de desinformación médica peruana

Repositorio de Seminario 1 para construir y evaluar un clasificador binario de
noticias médicas en español relacionadas con Perú.

La unidad de predicción es el texto de la noticia y la única variable objetivo
es:

```text
REAL | FAKE
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
  → etiquetas REAL/FAKE
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
cp data/source_urls.example.csv data/raw/source_urls.csv

python3 -m venv .venv
.venv/bin/python -m pip install -e '.[scraping]'

.venv/bin/python scripts/01_collect_sources.py \
  --config configs/sources.yaml \
  --urls-file data/raw/source_urls.csv \
  --output data/raw/articles.jsonl
```

El manifiesto local debe contener al menos `url` y `source_id`. Las páginas
descargadas y los textos derivados quedan fuera de Git. Antes de recolectar se
deben revisar los términos de uso, robots.txt, límites de consulta y permisos
de cada fuente.

Después se prepara la hoja de anotación:

```bash
.venv/bin/python scripts/02_prepare_annotation.py \
  --input data/raw/articles.jsonl \
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
│   ├── processed/                # dataset binario final
│   └── source_urls.example.csv   # plantilla versionada
├── docs/methodology.md           # protocolo metodológico
├── scripts/
│   ├── 01_collect_sources.py     # extracción dirigida
│   ├── 02_prepare_annotation.py  # plantilla de anotación
│   └── 03_build_binary_dataset.py
├── src/peruvian_medical_misinformation/
│   └── collection.py             # descarga y extracción de texto
└── tests/
```

## Modelo y evaluación

La comparación prevista es binaria y usa Macro-F1 como métrica principal,
acompañada de precision, recall, ROC-AUC y matriz de confusión. Las familias de
modelos se mantienen como experimentos de Seminario 1: TF-IDF con clasificadores
clásicos, embeddings de palabras, sentence transformers y transformers en
español. No se incluyen ranking, qrels, Triplet Loss, RAG, generación de
respuestas ni clasificación multiclase.

El piloto inicial será de 200 registros para comprobar las reglas de anotación.
La meta del corpus final es aproximadamente 1,000 registros válidos y
balanceados entre `REAL` y `FAKE`.

## Datos y credenciales

No se suben al repositorio textos descargados, claves de Scopus ni respuestas
completas de APIs. Se conserva la procedencia mediante URL, fuente, fecha,
estado de extracción y referencias de evidencia. El acceso a los artículos
debe respetar los permisos de cada fuente.
