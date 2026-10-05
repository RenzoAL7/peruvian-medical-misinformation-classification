# Corpus de noticias médicas peruanas

Este repositorio contiene el recolector y las OCI Functions del pipeline cloud del proyecto. Descubre noticias candidatas, conserva su trazabilidad y prepara el cuerpo textual para Silver. No decide si una noticia es médica ni asigna etiquetas de veracidad.

## Pipeline OCI en la nube

Las Functions desplegadas en OCI separan las etapas de datos:

1. `fetch-newsdata` consulta NewsData y escribe lotes deduplicados en `bronze/`.
2. `extract-news-body` recorre los CSV Bronze en orden, combina archivos para
   formar lotes de hasta 50 filas pendientes y escribe los cuerpos en `silver/`.
3. La revisión humana delimita la afirmación, reúne evidencia y asigna la
   etiqueta antes de construir Gold.

La extracción del cuerpo conserva estados `OK`, `CUERPO_INSUFICIENTE` y errores
HTTP para que una URL bloqueada no desaparezca del registro. El Function deja
un margen interno antes del límite de 300 segundos y continúa con las filas
pendientes en la siguiente ejecución.

## Flujo local de referencia

1. El Colab lee los `record_id` existentes en la pestaña `Bronze` de Google Sheets.
2. Ejecuta `scripts/01_collect_newsdata_urls.py` y le pasa esos identificadores para evitar repeticiones.
3. El recolector carga `configs/batch.yaml`, consulta secciones públicas de salud y guarda un CSV temporal de candidatas.
4. El Colab vuelve a comprobar los identificadores y anexa a `Bronze` únicamente las noticias nuevas.
5. El investigador revisa manualmente relevancia médica y elegibilidad de la afirmación.
6. El Colab descarga el cuerpo de las filas aprobadas y las agrega a `Silver` para la posterior validación con evidencia.
7. El Colab reconstruye `Gold` únicamente con noticias validadas, etiquetadas y aprobadas para entrenamiento.

## Medios y método de descubrimiento

Cada corrida intenta obtener hasta 12 candidatas textuales desde un conjunto
amplio de fuentes. Cada fuente aporta como máximo 2 noticias y la selección
final se hace por rondas, para evitar que un solo portal domine el lote.

| Medio | Sección pública verificada |
| --- | --- |
| El Comercio | `bienestar/salud-fisica` |
| La República | `salud` |
| Diario Correo | `salud` |
| Diario Ojo | `salud` |
| MINSA | `institucion/minsa/noticias` |
| Gestión | etiqueta `salud` |
| El Popular | `vida` |
| Canal N | etiqueta `salud` |

Las páginas se comprobaron con `robots.txt` y acceso real. El recolector acepta
únicamente enlaces internos descubiertos en esas páginas y exige que el título
o bajada contenga un término médico y una señal de afirmación contrastable. Las
candidatas se deduplican por URL canónica y `record_id`.

MINSA se registra con `source_dataset=archive_minsa_institucional`, porque es
una fuente institucional y no un medio periodístico. Sus comunicados son
candidatas útiles, pero no reciben automáticamente la etiqueta de verdadero ni
reemplazan la validación independiente con evidencia.

La configuración vigente no consume créditos de NewsData. La integración se conserva para pruebas futuras y, si se vuelve a habilitar, aplica `video=0`, `removeduplicate=1`, máximo 2 solicitudes por fuente y máximo 4 por corrida para proteger el plan gratuito.

Una corrida puede devolver menos de 12 candidatas nuevas si las páginas no contienen suficientes artículos que superen los filtros o si las URLs ya existen en `Bronze`. El reporte registra el resultado real; nunca se inventan URLs ni se reutilizan noticias existentes para completar el cupo.

### Frecuencia recomendada

- Ejecutar una corrida de 12 candidatas como máximo una vez cada 24 horas.
- Si la corrida devuelve pocas noticias nuevas, esperar 48 horas antes de repetirla.
- `request_delay_seconds: 1.0` solo separa solicitudes consecutivas dentro de
  una corrida; no obliga a esperar una hora o un día entre ejecuciones.
- Repetir el Colab inmediatamente suele devolver las mismas portadas y no
  acelera la construcción del corpus. Para recuperar noticias históricas se
  debe implementar paginación o rangos de fecha, no aumentar la frecuencia.

## Archivos del repositorio

```text
configs/
  batch.yaml                     fuentes, temas y límites de la corrida
scripts/
  01_collect_newsdata_urls.py    punto de entrada ejecutado por Colab
src/peruvian_medical_misinformation/
  __init__.py                    definición del paquete
  newsdata.py                    recolección, normalización y deduplicación
tests/
  test_newsdata_batch.py         pruebas del recolector
  test_batch_contract.py         protege las fuentes y la meta global del batch
  test_repository_hygiene.py     evita versionar datos CSV
docs/
  data_schema.md                 columnas de Bronze, Silver y Gold
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
make run EXISTING="/ruta/Corpus noticias medicas.xlsx"
```

La opción `EXISTING` debe apuntar a un Excel o CSV con una columna `record_id`. El archivo se usa solo para excluir noticias conocidas.

## Límites metodológicos

- NewsData y los archivos periodísticos son mecanismos de descubrimiento, no autoridades médicas.
- `api_query` conserva el tema o archivo que permitió descubrir la candidata.
- La persona investigadora decide `is_medical` e `is_claim_eligible`.
- La afirmación, evidencia, etiqueta y elegibilidad final se completan y validan en `Silver`.
- `Gold` contiene únicamente registros con extracción correcta, evidencia completa, etiqueta `RESPALDADA` o `REFUTADA`, validación completada y elegibilidad final aprobada.
- La fuente periodística, la URL, la fecha y el autor se conservan para auditoría, no para predecir la etiqueta.
- El historial de fuentes aceptadas y descartadas está documentado en `docs/source_audit.md`.
