# Diseño metodológico inicial

## Unidad de recuperación

La unidad que se recupera y ordena es un **documento de evidencia**: una nota, verificación, comunicado o contenido publicado por una fuente definida dentro del corpus. La interfaz puede agrupar después esos documentos por fuente o dominio.

## Ground truth de ranking

El dataset inicial proporciona contenido y etiquetas de veracidad, pero no una matriz de relevancia para recuperación. Por tanto, el *ground truth* del proyecto se construirá como un archivo de *qrels* que relaciona:

```text
consulta → documento candidato → nivel de relevancia
```

No se debe usar el conjunto completo de *qrels* para ajustar el modelo. Las particiones de validación y prueba se mantienen sin exponer al entrenamiento.

## Comparación experimental

La secuencia mínima será:

1. TF-IDF y similitud coseno como baseline léxico.
2. SBERT preentrenado y similitud coseno como baseline semántico.
3. SBERT ajustado con tripletas `(consulta, positivo, negativo)` creadas sólo desde los *qrels* de entrenamiento.
4. Comparación con P@k, R@k, MRR y nDCG@k sobre las mismas consultas de prueba.

## Explicabilidad

La explicación se definirá sobre una recomendación concreta. Debe mostrar, por ejemplo, términos o fragmentos que contribuyeron a la coincidencia, la fuente y las limitaciones del resultado. No se afirmará que SHAP explica directamente una similitud de embeddings sin implementar y validar un método de atribución adecuado.

## Criterio de éxito

El modelo ajustado deberá superar los baselines en las métricas de ranking predefinidas y los casos de error deberán revisarse cualitativamente. Un aumento aislado de una métrica no será suficiente si introduce sesgo hacia una fuente, tema o tipo de consulta.
