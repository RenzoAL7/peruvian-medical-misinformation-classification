# Recomendador de fuentes confiables en español con NLP y XAI

Sistema de recomendación de fuentes confiables de contenido digital en español mediante recuperación de información, modelos de lenguaje y explicabilidad.

**Nombre propuesto para GitHub:** `recomendador-fuentes-confiables-nlp-xai`

> Estado: estructura inicial del proyecto. Aún no contiene resultados experimentales ni el dataset original.

## Objetivo

Diseñar y evaluar un sistema que, dada una consulta o afirmación en español, recupere y ordene contenido de un corpus de evidencia confiable y entregue una recomendación de fuentes con una explicación comprensible de la coincidencia.

El sistema no pretende decidir automáticamente si una afirmación es verdadera o falsa. Su función principal es **recuperar evidencia relevante y priorizar sus fuentes**.

## Pregunta de investigación

¿En qué medida los modelos semánticos ajustados con aprendizaje por tripletas mejoran la recomendación de fuentes confiables en español, frente a baselines léxicos y semánticos sin ajuste, y cómo puede explicarse cada recomendación?

## Flujo metodológico

```text
Dataset inicial
  → auditoría y preprocesamiento
  → corpus de evidencia confiable
  → consultas + qrels (ground truth de relevancia)
  → baseline TF-IDF
  → baseline SBERT
  → SBERT con Triplet Loss
  → ranking de evidencia y agregación por fuente
  → evaluación (P@k, R@k, MRR, nDCG@k) + explicación
```

Las etiquetas `VERDADERO` y `FALSO` del dataset sirven para exploración y control de calidad, pero no sustituyen una etiqueta de relevancia entre una consulta y un documento. Por ello, el proyecto incorpora un conjunto de *qrels* (juicios de relevancia) independiente.

## Estructura del repositorio

```text
.
├── configs/                 # Configuraciones reproducibles de experimentos
├── data/
│   ├── raw/                 # Dataset original, no versionado
│   ├── interim/             # Datos temporales, no versionados
│   ├── processed/           # Datos procesados, no versionados
│   └── qrels/               # Especificación y futuros juicios de relevancia
├── docs/                    # Diseño metodológico y decisiones del proyecto
├── models/                  # Pesos locales, no versionados
├── notebooks/               # Exploración reproducible y análisis inicial
├── reports/figures/         # Figuras generadas para informes
├── scripts/                 # Puntos de entrada de ejecución
├── src/recom_fuentes/       # Código Python del proyecto
│   ├── data/                # Carga, auditoría y preprocesamiento
│   ├── ground_truth/        # Construcción y validación de qrels
│   ├── retrieval/           # Baselines, embeddings y ranking
│   ├── evaluation/          # Métricas y análisis de errores
│   └── explainability/      # Explicaciones de las recomendaciones
└── tests/                   # Pruebas automatizadas
```

## Datos

El dataset original se mantiene fuera de Git. Para trabajar localmente, colócalo en `data/raw/` y registra en la documentación su versión, fecha de obtención y hoja de origen.

Para el archivo `Dataset FakeNewsEspañol2024`, se usará la hoja maestra `DATASET ULIMA 1189` como punto de partida, sin concatenar las hojas auxiliares. Antes de cualquier entrenamiento se deberá:

1. revisar campos vacíos, IDs repetidos y duplicados textuales;
2. normalizar categorías, tildes y etiquetas;
3. definir un corpus de evidencia de fuentes verificadas;
4. crear y validar los *qrels* de consulta–documento;
5. separar entrenamiento, validación y prueba sin fuga de información.

La procedencia de un post en una red social no se tratará por sí sola como señal de confiabilidad: el ranking se basará primero en documentos de evidencia y luego se agregará por fuente.

## Plan de experimentos

| Etapa | Modelo / producto | Métrica principal |
| --- | --- | --- |
| 1 | Auditoría, limpieza y catálogo de datos | cobertura y calidad de registros |
| 2 | Qrels y protocolo de anotación | acuerdo y consistencia de relevancia |
| 3 | TF-IDF + similitud coseno | P@k, R@k, MRR, nDCG@k |
| 4 | SBERT preentrenado | P@k, R@k, MRR, nDCG@k |
| 5 | SBERT ajustado con Triplet Loss | P@k, R@k, MRR, nDCG@k |
| 6 | Explicación local de la recomendación | evaluación cualitativa y casos de error |

## Reproducibilidad

- Fijar semilla, versiones, configuración y particiones de datos por experimento.
- Guardar métricas y parámetros en `reports/` o en un rastreador de experimentos cuando se incorpore.
- No subir archivos crudos, credenciales, pesos grandes ni resultados temporales.
- Usar únicamente los *qrels* de entrenamiento para construir tripletas; validación y prueba deben mantenerse separadas.

## Próximos pasos

1. Crear el diccionario de datos y el notebook de auditoría.
2. Definir qué fuentes formarán el corpus de evidencia confiable.
3. Redactar el protocolo para crear los *qrels*.
4. Implementar el baseline TF-IDF antes de ajustar SBERT.

## Licencia y atribución

Antes de publicar el dataset o cualquier contenido recuperado, verificar sus permisos de uso, anonimización y condiciones de atribución.
