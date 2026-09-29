# Corpus de noticias médicas peruanas

Este repositorio contiene únicamente el recolector utilizado por el notebook de Google Colab del proyecto. Su función es descubrir noticias candidatas y conservar su trazabilidad. No decide si una noticia es médica ni asigna etiquetas de veracidad.

## Flujo vigente

1. El Colab lee los `record_id` existentes en la pestaña `Raw` de Google Sheets.
2. Ejecuta `scripts/01_collect_newsdata_urls.py` y le pasa esos identificadores para evitar repeticiones.
3. El recolector carga `configs/batch_12.yaml`, consulta secciones públicas de salud y guarda un CSV temporal de candidatas.
4. El Colab vuelve a comprobar los identificadores y anexa a `Raw` únicamente las noticias nuevas.
5. El investigador revisa manualmente relevancia médica y elegibilidad de la afirmación.
6. El Colab descarga el cuerpo de las filas aprobadas y las agrega a `Extraccion` para la posterior validación con evidencia.

## Medios y método de descubrimiento

Cada corrida intenta obtener hasta 12 candidatas textuales: 3 por cada medio.

| Medio | Sección pública verificada |
| --- | --- |
| El Comercio | `bienestar/salud-fisica` |
| La República | `salud` |
| Diario Correo | `salud` |
| Diario Ojo | `salud` |

Las cuatro secciones fueron comprobadas con `robots.txt` y con extracción real de cuerpos. El recolector acepta únicamente URLs internas de esas secciones y exige que el título o bajada contenga un término médico y una señal de afirmación contrastable. Las candidatas se deduplican por URL canónica y `record_id`.

La configuración vigente no consume créditos de NewsData. La integración se conserva para pruebas futuras y, si se vuelve a habilitar, aplica `video=0`, `removeduplicate=1`, máximo 2 solicitudes por fuente y máximo 4 por corrida para proteger el plan gratuito.

Una corrida puede devolver menos de 12 candidatas nuevas si las páginas no contienen suficientes artículos que superen los filtros o si las URLs ya existen en `Raw`. El reporte registra el resultado real; nunca se inventan URLs ni se reutilizan noticias existentes para completar el cupo.

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
