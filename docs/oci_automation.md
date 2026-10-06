# Automatización OCI del pipeline

Este documento describe los recursos que deben existir en el tenancy. Los
OCID concretos se mantienen en la configuración de OCI y no en el repositorio.

## Frecuencia

Resource Scheduler inicia `fetch-newsdata` dos veces al día, a las 08:00 y
20:00 en `America/Lima`. Resource Scheduler interpreta el cron en UTC, por
eso las expresiones configuradas son `0 13 * * *` y `0 1 * * *`. La Function
solicita hasta 50 filas nuevas por corrida; si la API devuelve menos, escribe
el CSV disponible. El siguiente paso no depende de que el lote llegue
exactamente a 50.

Para controlar el consumo de NewsData, la configuración de producción usa
`NEWSDATA_SIZE=10` y `NEWSDATA_MAX_PAGES=2`. Como hay cuatro grupos de países,
el recolector puede hacer como máximo ocho solicitudes por corrida y se detiene
antes cuando alcanza las 50 filas nuevas. Cada solicitud adicional consume un
crédito de NewsData, por lo que no se dejan ocho páginas por grupo como valor
predeterminado.

Además, `extract-news-body`, `extract-claims` y
`retrieve-pubmed-evidence` tienen un drenaje horario (`0 * * * *`, UTC). Esas
invocaciones no recolectan noticias: recorren los CSV pendientes, completan los
lotes que no alcanzaron a procesarse y reintentan únicamente los errores
transitorios. Si no hay trabajo pendiente, terminan sin escribir un CSV nuevo.

## Encadenamiento por eventos

OCI Events escucha la creación de estos objetos y llama a una Function:

| Evento | Prefijo creado | Function llamada |
| --- | --- | --- |
| Object Storage `CreateObject` | `bronze/*.csv` | `extract-news-body` |
| Object Storage `CreateObject` | `silver/body/*.csv` | `extract-claims` |
| Object Storage `CreateObject` | `silver/claims/*.csv` | `retrieve-pubmed-evidence` |

Cada regla filtra también `bucketName=mednews-data`. No se crea una regla para
`silver/evidence/`, porque la revisión de etiquetas permanece bajo control
humano en Label Studio.

## Orden y tamaño de los lotes

| Capa | Function | Máximo por invocación | Resultado |
| --- | --- | ---: | --- |
| Bronze | `fetch-newsdata` | 50 noticias nuevas | `bronze/newsdata_<run_id>.csv` |
| Silver body | `extract-news-body` | 50 filas | `silver/body/body_<run_id>.csv` |
| Silver claims | `extract-claims` | 10 filas, una solicitud Gemini por lote | `silver/claims/claims_<run_id>.csv` |
| Silver evidence | `retrieve-pubmed-evidence` | 5 claims | `silver/evidence/evidence_<run_id>.csv` |

Los lotes pequeños de claims y evidence se drenan cada hora para que una
corrida de 50 noticias no quede limitada al primer evento de Object Storage.

Evidence guarda hasta 10 candidatos PubMed dentro de
`pubmed_results_json`. Eso son diez candidatos por claim, no diez filas
adicionales. La puntuación `embedding_similarity` de OCI Embed 4 ordena la
lista; el valor no es una probabilidad de veracidad. La etiqueta final se
asigna en Label Studio.

## Claves Gemini

| Secretos de Vault | Stage | Uso |
| --- | --- | --- |
| `google-gemini-api-key`, `google-gemini-api-key-2` | claims | extracción del claim, traducción fiel a inglés y `pubmed_query_en` |
| `google-gemini-api-key-3`, `google-gemini-api-key-4` | evidence | traducción de abstracts a español |

Cada Function carga los secretos durante la invocación y alterna entre ellos.
Si un proyecto responde por cuota, autenticación o rate limit, prueba el
siguiente slot. Las claves nunca entran al CSV, la imagen ni el repositorio.

## Reintentos y duplicados

El estado se deriva de `record_id`. Un resultado terminal (`OK`,
`CUERPO_INSUFICIENTE`, `NO_RESULTS`, `NO_ABSTRACT`, o un error permanente de
URL) no se vuelve a procesar. Un timeout, error de red, HTTP 429 o HTTP 5xx se
conserva para auditoría y se reintenta en la siguiente ejecución.

## Similitud y umbral

No se fija un umbral universal como `0.87` antes de calibrar. Scores de
embeddings distintos no son comparables: la escala depende del modelo y del
texto, y `0.3683` puede ser un score TF-IDF o un score de otro modelo. Se
guardan los 10 candidatos para revisión; después de etiquetar una muestra de
al menos 30 claims, se elige un umbral con una tabla de precisión/recall y se
documenta la decisión en la metodología. Una fila no entra a Gold por superar
una puntuación automática.
