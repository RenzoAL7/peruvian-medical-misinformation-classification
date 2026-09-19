# Diseño metodológico de Seminario 1

## 1. Propósito y límite

El sistema recibe una consulta o afirmación en español y recupera documentos de evidencia relacionados, ordenándolos según su relevancia. El resultado es una recomendación de evidencias y fuentes, no una sentencia automática de verdad o falsedad.

Seminario 1 termina después de obtener y evaluar el ranking. Las APIs externas, la consulta en tiempo real, RAG y la generación de una respuesta citada quedan para una etapa posterior.

## 2. Unidad de recuperación

La unidad recuperada es un **documento de evidencia**: una verificación, nota, comunicado o publicación perteneciente al corpus definido. La interfaz podrá agrupar resultados por fuente o dominio después, pero la evaluación se realiza primero sobre documentos.

## 3. Adaptación del dataset

`FakeNewsEspañol2024` es el punto de partida, no el ground truth final del ranking. Sus etiquetas `VERDADERO` y `FALSO` describen el registro original, pero no indican si un documento es relevante para una consulta.

El dataset adaptado debe conservar la trazabilidad y separar como mínimo:

- `Claims`: identificador y texto de la afirmación o consulta.
- `Evidence`: identificador, texto, URL, fuente, dominio y estado de extracción.
- `Relevance_Judgments`: relación consulta–evidencia con relevancia `0`, `1` o `2`.
- `Triplets`: consulta, evidencia positiva y evidencia negativa para entrenamiento.

La anotación de relevancia debe revisarse manualmente. No se debe convertir automáticamente `LINK` en evidencia positiva, porque puede apuntar a un artículo de verificación y no a la fuente original. Las URLs duplicadas y las evidencias sin texto deben registrarse, no ocultarse.

## 4. Flujo experimental

```text
Raw original
  → auditoría y preservación
  → limpieza, normalización y tokenización
  → Claims + Evidence
  → qrels de train/validation/test
  → generación de tripletas desde train
  → cuatro métodos de recuperación
  → ranking de evidencias
  → métricas y análisis de errores
```

Las particiones deben evitar fuga de información por documento o URL. Las tripletas sólo pueden construirse con los juicios de relevancia de entrenamiento.

## 5. Enfoques comparados

### 5.1 TF-IDF + similitud coseno

Representa la consulta y los documentos mediante pesos léxicos. La similitud coseno ordena los documentos por coincidencia de términos. Es un baseline y no aprende parámetros mediante etiquetas de relevancia.

### 5.2 BM25

Calcula una puntuación de recuperación léxica considerando frecuencia de términos, frecuencia documental y longitud del documento. Su puntuación no debe interpretarse como una similitud coseno.

### 5.3 SBERT preentrenado

Transforma la consulta y cada evidencia en embeddings semánticos usando pesos preentrenados. La similitud coseno permite ordenar textos relacionados incluso cuando no comparten exactamente las mismas palabras.

### 5.4 SBERT ajustado con Triplet Loss

Parte de SBERT y ajusta sus representaciones con tripletas revisadas:

```text
(consulta, evidencia positiva, evidencia negativa)
```

El objetivo es acercar la consulta a la evidencia positiva y alejarla de la negativa. El ajuste debe hacerse sólo con tripletas de entrenamiento; después se evalúa con consultas y evidencias no expuestas durante el ajuste.

## 6. Evaluación

Cada método produce un ranking para las mismas consultas de prueba. Se calculan:

- `Precision@k`: proporción de resultados relevantes dentro de los primeros `k`.
- `Recall@k`: proporción de evidencias relevantes recuperadas en los primeros `k`.
- `MRR`: posición de la primera evidencia relevante.
- `nDCG@k`: calidad del orden considerando grados de relevancia.

Se deben fijar los mismos valores de `k`, consultas y qrels para los cuatro métodos. También conviene registrar tiempo de respuesta y casos de error, pero no sustituir las métricas de ranking por accuracy o F1.

## 7. Criterio de cierre de Seminario 1

El núcleo estará listo cuando:

1. el dataset adaptado tenga trazabilidad y controles de calidad;
2. los qrels y tripletas estén revisados y particionados sin fuga;
3. los cuatro enfoques produzcan rankings reproducibles;
4. las métricas se calculen sobre las mismas consultas de prueba;
5. se documenten resultados, errores, limitaciones y diferencias entre métodos.

La minisimulación del notebook valida la mecánica del flujo, pero sus resultados no deben presentarse como evidencia experimental final porque utiliza un corpus sintético pequeño.
