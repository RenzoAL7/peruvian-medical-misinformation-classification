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

## Presupuesto de tiempo

El timeout síncrono máximo de OCI Functions es de 300 segundos. Para no llegar
al borde, las cuatro Functions tienen un presupuesto interno de 240 segundos y
un margen de 10 segundos para terminar la escritura del objeto:

```text
NEWSDATA_MAX_SECONDS=240       NEWSDATA_TIME_BUFFER=10
BODY_MAX_SECONDS=240           BODY_TIME_BUFFER=10
LLM_MAX_SECONDS=240            LLM_TIME_BUFFER=10
EVIDENCE_MAX_SECONDS=240
```

Los valores son límites de trabajo, no duraciones garantizadas. El lote real
puede ser menor si las URLs son lentas, si el proveedor agota la cuota o si ya
existe el `record_id`. Cada Function escribe las filas que alcanzó a completar
y el drenaje horario continúa con las pendientes. Para invocación manual usa
`--read-timeout 360`; ese parámetro pertenece al cliente OCI y no amplía el
límite de 300 segundos de la Function.

La tabla completa, incluida la duración de cada solicitud, el consumo y la
matriz de estados, está en
[`limits_and_timing.md`](limits_and_timing.md).

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

## Restricciones externas que afectan la automatización

- **NewsData:** `size=10` y dos páginas por grupo producen como máximo ocho
  solicitudes por corrida con la configuración actual. Cada página puede
  consumir un crédito. `totalResults` describe resultados disponibles y no
  equivale a `row_count`; la ventana reciente puede repetir URLs. La consulta
  se mantiene por debajo de 100 caracteres por el error observado en esta
  cuenta. Revisar el saldo y el límite del plan antes de aumentar frecuencia o
  páginas.
- **Gemini:** RPM, TPM y RPD son límites por proyecto y modelo. Las cuatro
  claves pertenecen a proyectos diferentes y se usan como failover; no se
  asume que una clave adicional multiplica la cuota de un proyecto. Las claves
  solo se leen desde Vault durante la invocación.
- **PubMed:** la Function respeta una pausa de 0.4 s y agrupa los PMIDs en
  EFetch. Mantener `PUBMED_EMAIL` y `PUBMED_TOOL` configurados y no enviar
  consultas en paralelo sin revisar las reglas de NCBI.
- **OCI Embed 4:** el modelo `cohere.embed-v4.0` usa 512 dimensiones en este
  pipeline y se limita por caracteres antes de crear embeddings. La API/SDK
  admite hasta 128.000 tokens de entrada total por ejecución; las cuotas y la
  disponibilidad dependen de la región.
- **Scheduler:** interpreta cron en UTC, tiene intervalo mínimo de una hora y
  no ajusta automáticamente el horario de verano. Las horas de inicio pueden
  retrasarse por la cola del servicio.
- **Events y Object Storage:** Events es asíncrono y puede entregar un evento
  después de un retry; Object Storage usa prefijos, no carpetas POSIX. La
  deduplicación por `record_id` y el drenaje horario hacen segura la repetición.

Enlaces oficiales y detalles de cada límite: [OCI Functions](https://docs.oracle.com/en-us/iaas/Content/Functions/Tasks/functionscustomizing.htm),
[Resource Scheduler](https://docs.oracle.com/en-us/iaas/Content/resource-scheduler/tasks/create-manage.htm),
[Object Storage](https://docs.oracle.com/en-us/iaas/Content/Object/Concepts/objectstorageoverview.htm),
[OCI Generative AI](https://docs.oracle.com/en-us/iaas/Content/generative-ai/limits.htm),
[NewsData](https://newsdata.io/documentation) y
[NCBI E-utilities](https://www.ncbi.nlm.nih.gov/books/NBK25497/?report=printable).

## Despliegue de la imagen

Las Functions se ejecutan con la forma `GENERIC_X86` y memoria de 512 MB. Al
construir desde Apple Silicon, conserva la plataforma de OCI, por ejemplo:

```bash
DOCKER_DEFAULT_PLATFORM=linux/amd64 fn deploy --local
```

El comando exacto depende de la aplicación y el OCIR configurados; no se deben
subir claves ni archivos `.env` a la imagen.

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
