# Qrels: juicios de relevancia para ranking

Un *qrel* es un juicio que indica si un documento de evidencia es relevante para
una consulta. Este proyecto necesita los *qrels* porque una etiqueta
`VERDADERO` o `FALSO` de un registro no expresa por sí misma la relación
consulta–documento.

## Esquema mínimo

| Campo | Descripción |
| --- | --- |
| `query_id` | Identificador estable de la consulta o afirmación. |
| `candidate_id` | Identificador estable del documento de evidencia. |
| `source_id` | Fuente o dominio del documento candidato. |
| `relevance` | 0 = no relevante, 1 = parcialmente relevante, 2 = relevante. |
| `split` | `train`, `validation` o `test`. |
| `annotator_id` | Identificador seudonimizado de quien anotó. |
| `notes` | Justificación breve o enlace de verificación, si corresponde. |

## Reglas de anotación

1. Definir la consulta antes de elegir sus candidatos.
2. Anotar al menos un candidato relevante y uno no relevante por consulta.
3. Usar `2` para evidencia directa, `1` para contexto útil y `0` para evidencia no relevante.
4. Mantener consultas y candidatos de validación/prueba fuera de las tripletas de entrenamiento.
5. Conservar una guía de anotación y, si hay más de una persona anotando, medir acuerdo entre anotadores.
6. No convertir automáticamente `LINK`, el nombre de una red social o la etiqueta de veracidad en una fuente confiable.

## Tripletas

Las tripletas se construyen únicamente después de revisar los qrels de
entrenamiento:

```text
(query_id, candidate_id con relevancia 2, candidate_id con relevancia 0)
```

Los negativos pueden ser difíciles y pertenecer al mismo tema, pero no deben
ser positivos ocultos. La división de datos debe evitar que la misma URL o
documento aparezca en entrenamiento y prueba.
