# Recomendador de fuentes confiables en español

Repositorio base de la tesis para **Seminario 1**. El núcleo actual recupera y
ordena evidencias en español relacionadas con una consulta o afirmación. No
clasifica automáticamente la verdad de una afirmación.

## Alcance actual

El flujo de Seminario 1 termina en el ranking y la evaluación de evidencias:

```text
Dataset original
  → auditoría y preprocesamiento
  → Claims + Evidence
  → qrels de relevancia + tripletas
  → recuperación con cuatro enfoques
  → ranking por similitud o puntuación
  → Precision@k, Recall@k, MRR y nDCG@k
```

Los cuatro enfoques comparados son:

1. TF-IDF + similitud coseno.
2. BM25.
3. SBERT preentrenado + similitud coseno.
4. SBERT ajustado con Triplet Loss + similitud coseno.

TF-IDF y BM25 son baselines de recuperación. SBERT preentrenado genera
embeddings con pesos existentes y Triplet Loss ajusta SBERT usando relaciones
`consulta–positivo–negativo` revisadas.

La similitud indica relación textual o semántica; no demuestra que una noticia
sea verdadera o falsa.

## Qué queda fuera por ahora

- APIs externas y consulta de noticias en tiempo real.
- RAG, LLM y generación de respuestas citadas.
- Clasificación automática de veracidad.
- Módulos de explicabilidad y agregación avanzada por fuente.

Estas piezas podrán incorporarse después de cerrar el corpus, los qrels y la
evaluación de Seminario 1.

## Estructura mínima

```text
.
├── configs/base.yaml                    # parámetros reproducibles
├── data/
│   ├── raw/                              # dataset original, no versionado
│   ├── interim/                          # auditorías y transformaciones temporales
│   ├── processed/                        # Claims y Evidence preparados
│   └── qrels/                            # relevancia y tripletas revisadas
├── docs/methodology.md                   # contrato metodológico de Seminario 1
├── notebooks/00_minisimulacion_query_coseno.ipynb
├── src/recom_fuentes/
│   ├── data/                             # carga y preprocesamiento
│   ├── ground_truth/                     # qrels y tripletas
│   ├── retrieval/                        # cuatro enfoques de recuperación
│   └── evaluation/                       # métricas de ranking
└── tests/                                # pruebas del núcleo
```

## Estado real

La minisimulación del notebook funciona con un corpus sintético y demuestra el
flujo completo. Sus métricas no son resultados finales de la tesis. El siguiente
trabajo consiste en adaptar `FakeNewsEspañol2024` a un conjunto de claims,
documentos de evidencia y juicios de relevancia revisados por personas.

## Instalación

Desde la raíz del repositorio:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e .
.venv/bin/python -m ipykernel install --user \
  --name recomendador-fuentes-confiables \
  --display-name "Python (recomendador-fuentes-confiables)"
```

Para ejecutar también SBERT real y Triplet Loss:

```bash
.venv/bin/python -m pip install -e '.[sbert]'
```

En VS Code se debe seleccionar `.venv/bin/python` como kernel del notebook.

## Reglas de datos

- Mantener el archivo original fuera de Git y sin modificaciones.
- No convertir automáticamente `VERDADERO/FALSO` en juicios de relevancia.
- No convertir automáticamente `LINK` en evidencia positiva.
- Construir tripletas sólo con qrels de entrenamiento.
- Separar entrenamiento, validación y prueba sin fuga por URL o documento.
- Registrar procedencia, estado de extracción y límites de cada evidencia.

Antes de publicar datos o contenido recuperado, revisar permisos, anonimización
y condiciones de atribución.
