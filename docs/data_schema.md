# Esquema de datos vigente

Google Sheets es el espacio de trabajo del corpus. El flujo sigue una organización Medallion con las pestañas `Bronze`, `Silver` y `Gold`.

## Bronze

Una fila representa una noticia candidata todavía no validada. Se mantienen solo nueve campos:

| Campo | Uso |
| --- | --- |
| `record_id` | Hash estable de la URL canónica; se usa para deduplicar. |
| `source_name` | Medio o institución de procedencia. |
| `canonical_url` | URL normalizada que permite volver a la noticia original. |
| `published_at` | Fecha publicada cuando la fuente la entrega. |
| `title`, `subtitle_or_bajada` | Texto visible para decidir si la candidata merece revisión. |
| `topic` | Tema o archivo público que permitió descubrirla. |
| `selection_status` | `PENDIENTE`, `INCLUIR`, `EXCLUIR_NO_MEDICA`, `EXCLUIR_SIN_AFIRMACION` o `EXCLUIR_SIN_TEXTO`. |
| `retrieved_at` | Fecha UTC de recuperación. |

El Colab elimina duplicados dentro de la corrida y vuelve a consultar los `record_id` existentes inmediatamente antes de anexar.

## Silver

Solo recibe filas de `Bronze` con `selection_status=INCLUIR` y un cuerpo de al menos 150 palabras y 800 caracteres. Se limita a doce campos:

| Campo | Uso |
| --- | --- |
| `record_id`, `source_name`, `topic`, `title`, `canonical_url` | Identidad y trazabilidad mínima de la noticia. |
| `body` | Texto principal descargado desde la URL pública. |
| `main_medical_claim` | Afirmación médica principal delimitada manualmente. |
| `label` | `PENDIENTE`, `RESPALDADA`, `REFUTADA`, `NO_CONCLUYENTE` o `EXCLUIDA`. |
| `evidence_url` | Fuente especializada usada para contrastar la afirmación. |
| `verification_note` | Explicación breve de por qué la evidencia respalda, refuta o no permite concluir. |
| `reviewer`, `validation_status` | Responsable y estado `PENDIENTE` o `COMPLETADA`. |

La extracción del cuerpo no asigna una etiqueta. Si el texto no alcanza el mínimo, no se crea una fila en Silver y Bronze cambia a `EXCLUIR_SIN_TEXTO`. Las decisiones médicas y de veracidad siguen siendo humanas y basadas en evidencia.

## Gold

Es una salida generada y no debe editarse manualmente. Solo incluye noticias de `Silver` que cumplen simultáneamente:

- `validation_status=COMPLETADA`;
- etiqueta binaria `RESPALDADA` o `REFUTADA`;
- `body`, `main_medical_claim` y `evidence_url` no vacíos.

Una fila por `record_id` conserva siete campos: `record_id`, `topic`, `source_name`, `title`, `body`, `label` y `dataset_split`. Para entrenar, se concatena `title + body` como entrada y se usa `label` como objetivo. `source_name` y `topic` no son variables predictoras. `dataset_split` permanece vacío hasta aplicar la partición estratificada 70/15/15.

## Artefactos temporales

- `data/00_control/run_registry.csv`: estado y cantidades de cada ejecución local.
- `data/01_candidates/<run_id>.csv`: salida temporal consumida por el Colab.
- `reports/runs/<run_id>.json`: temas intentados, resultados por medio, duplicados y límites encontrados.

Estos archivos están ignorados por Git y no constituyen el corpus final.
