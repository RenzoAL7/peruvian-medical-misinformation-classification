# Corpus de noticias médicas peruanas

Este repositorio contiene únicamente el recolector utilizado por el [notebook de Google Colab](https://colab.research.google.com/drive/1he9_gDLiOBVrkqHuK1PynkTCps4_6OeN). Su función es descubrir noticias candidatas y conservar su trazabilidad. No decide si una noticia es médica ni asigna etiquetas de veracidad.

## Flujo vigente

1. El Colab lee los `record_id` existentes en la pestaña `Raw` de Google Sheets.
2. Ejecuta `scripts/01_collect_newsdata_urls.py` y le pasa esos identificadores para evitar repeticiones.
3. El recolector carga `configs/batch_12.yaml`, consulta archivos públicos y NewsData, y guarda un CSV temporal de candidatas.
4. El Colab vuelve a comprobar los identificadores y anexa a `Raw` únicamente las noticias nuevas.
5. El investigador revisa manualmente relevancia médica y elegibilidad de la afirmación.
6. El Colab descarga el cuerpo de las filas aprobadas y las agrega a `Extraccion` para la posterior validación con evidencia.

## Medios y método de descubrimiento

Cada corrida intenta obtener hasta 12 candidatas: 2 por cada medio.

| Medio | Método principal | Respaldo |
| --- | --- | --- |
| El Comercio | NewsData | — |
| RPP Noticias | NewsData | — |
| Latina Noticias | Archivo público de Salud/Medicina | NewsData |
| El Peruano | NewsData | — |
| Perú21 | Archivo público de Salud | NewsData |
| La República | NewsData | — |

Los archivos públicos de Latina y Perú21 se procesan antes de consumir créditos de NewsData. Las consultas API se reparten por rondas entre los medios pendientes y el primer tema rota entre corridas. Los temas configurados son `salud`, `medicina`, `enfermedad`, `tratamiento`, `medicamento`, `vacuna`, `síntomas`, `prevención`, `cáncer` y `diabetes`.

El endpoint `latest` puede devolver menos de 12 candidatas nuevas si no existen publicaciones recientes suficientes o si la cuenta alcanza su límite temporal. El reporte registra el resultado real; nunca se inventan URLs ni se reutilizan noticias existentes para completar el cupo.

## Archivos del repositorio

```text
configs/
  batch_12.yaml                  seis medios, temas y límites de la corrida
scripts/
  01_collect_newsdata_urls.py    punto de entrada ejecutado por Colab
src/peruvian_medical_misinformation/
  __init__.py                    definición del paquete
  newsdata.py                    recolección, normalización y deduplicación
tests/
  test_newsdata_batch.py         pruebas del recolector
  test_batch_12_contract.py      protege los seis medios y el batch 2 × 6
  test_repository_hygiene.py     evita versionar datos CSV
docs/
  data_schema.md                 columnas de Raw y Extraccion
  methodology.md                 metodología implementada
data/00_control/                 registro temporal de corridas
data/01_candidates/              CSV temporal de cada corrida
reports/runs/                    diagnóstico JSON temporal de cada corrida
```

Los CSV, reportes, credenciales y cuerpos de noticias no se versionan en Git.

## Ejecución local opcional

El flujo oficial se ejecuta desde Colab. Estos comandos solo sirven para verificar o probar el recolector localmente.

```bash
make setup
make test
make plan
```

Para una corrida local, copia `.env.example` como `.env`, agrega `NEWSDATA_API_KEY` y ejecuta:

```bash
make run EXISTING="/ruta/Excel Revision.xlsx"
```

La opción `EXISTING` debe apuntar a un Excel o CSV con una columna `record_id`. El archivo se usa solo para excluir noticias conocidas.

## Límites metodológicos

- NewsData y los archivos periodísticos son mecanismos de descubrimiento, no autoridades médicas.
- `api_query` conserva el tema o archivo que permitió descubrir la candidata.
- La persona investigadora decide `is_medical` e `is_claim_eligible`.
- La afirmación, evidencia, etiqueta y elegibilidad final se completan y validan en `Extraccion`.
- La fuente periodística, la URL, la fecha y el autor se conservan para auditoría, no para predecir la etiqueta.
