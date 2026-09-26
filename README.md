# Sistema de clasificación binaria de desinformación médica peruana

El trabajo activo de este repositorio es exclusivamente la fase 1: construir un
corpus trazable de noticias médicas peruanas en español. No se entrenan todavía
los ocho modelos de clasificación.

El corpus combina las noticias de Salud proporcionadas por el profesor
(`source_dataset=edwin_157`) con noticias públicas de RPP, El Comercio y Latina
(`scraped_rpp`, `scraped_el_comercio`, `scraped_latina`). La fuente, URL, fecha
y autor se conservan como metadatos y nunca asignan una etiqueta automática.

## Cómo ejecutar la fase 1

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[scraping,corpus,dev]'
.venv/bin/python -m pytest -q

# 1. Integra el XLSX original sin modificarlo.
.venv/bin/python scripts/00_import_edwin_157.py \
  --input "/ruta/Dataset FakeNewsEspañol2024.xlsx" \
  --sheet "DATASET ULIMA 1189"

# 2. Comprueba que período, robots, términos y rutas internas estén registrados.
.venv/bin/python scripts/01_discover_urls.py --dry-run

# 3. Tras completar esa configuración, descubre y extrae URLs públicas.
.venv/bin/python scripts/01_discover_urls.py
.venv/bin/python scripts/02_collect_articles.py

# 4. Consolida CSV, Parquet y resumen. Exige al menos 200 registros únicos válidos.
.venv/bin/python scripts/03_consolidate_corpus.py --require-minimum

# 5. Genera la plantilla Human-in-the-Loop cuando se alcance el mínimo.
.venv/bin/python scripts/04_prepare_annotation.py
```

La extracción masiva permanece bloqueada mientras no se definan
`collection.period.start/end` y las revisiones de `robots.txt`, términos y
rutas públicas en `configs/sources.yaml`. El scraper no usa Google ni otro
buscador: trabaja con categoría, RSS, sitemap o archivo público configurado.

El mínimo antes de la anotación completa es **200 noticias válidas y no
duplicadas**. Los resultados se escriben en
`data/processed/medical_news_corpus.csv`,
`data/processed/medical_news_corpus.parquet` y
`reports/collection_summary.json`. El resumen desglosa registros por fuente,
válidos únicos, duplicados, errores, exclusiones y campos faltantes.

La etiqueta de revisión humana es `0`, `1` o `EXCLUIDA`. La etiqueta original
de Edwin se mantiene en `source_original_label`; no se traduce automáticamente
porque su equivalencia debe validarse con evidencia médica.

Consulta [el esquema de datos](docs/data_schema.md) para los campos obligatorios.

## Alcance metodológico

```text
datos existentes + URLs públicas permitidas
  → preservación de HTML, URL, fecha y procedencia
  → extracción y normalización de texto
  → hashes y deduplicación
  → corpus CSV/Parquet + informe de cobertura
  → plantilla Human-in-the-Loop
  → revisión de evidencia y etiqueta 0/1/EXCLUIDA
  → división estratificada posterior (70/15/15)
```

La división y el entrenamiento están fuera de esta entrega. Solo se harán tras
deduplicar y completar la revisión humana. El conjunto de prueba final no se
usará para entrenar, ajustar hiperparámetros ni seleccionar modelos.

## Controles de extracción

Scrapy organiza las solicitudes y reintentos. La configuración aplica espera
entre peticiones, una sola solicitud concurrente por dominio, caché local,
backoff exponencial acotado, límite de páginas, profundidad limitada y un
User-Agent descriptivo. Trafilatura
extrae el cuerpo principal y BeautifulSoup se usa únicamente como respaldo.

El HTML original se guarda en `data/raw/html/` con una ruta nueva por descarga;
no se sobrescribe. Cada corrida deja JSONL de metadatos, `scraped_news.jsonl` y
`extraction_log.csv` con éxitos, errores, exclusiones y duplicados.

## Estructura relevante

```text
configs/                       # período, límites y fuentes aprobadas
data/raw/html/                 # HTML original versionado, ignorado por Git
data/raw/metadata/             # metadatos por fuente o corrida, ignorados
data/interim/                  # URLs descubiertas, JSONL y log de extracción
data/processed/                # CSV y Parquet consolidados, ignorados
data/annotations/              # plantilla de revisión humana, ignorada
docs/data_schema.md            # diccionario de datos
scripts/00_import_edwin_157.py
scripts/01_discover_urls.py
scripts/02_collect_articles.py
scripts/03_consolidate_corpus.py
scripts/04_prepare_annotation.py
src/peruvian_medical_misinformation/corpus.py
src/peruvian_medical_misinformation/spiders.py
tests/
```

## Datos y referencias

No se suben al repositorio textos descargados, HTML, claves, cookies ni
credenciales. El código conserva los metadatos necesarios para reproducir y
auditar la recolección local.

## Relación con antecedentes

- Pande et al. (2022): guía la conexión entre adquisición automática y
  clasificación textual, sin que la fuente defina la veracidad.
- Bonet-Jover et al. (2023): respalda la doble revisión Human-in-the-Loop.
- Noor et al. (2025) y Obunadike et al. (2025): motivan limpieza y
  normalización que preserve tildes y negaciones relevantes.
- Blanco-Fernández et al. (2024): motiva conservar fuente y duplicados para
  estudiar la generalización entre medios.
- Nina et al. (2025) y Alghamdi et al. (2023): motivan la comparación posterior
  de enfoques tradicionales, profundos y Transformer en español y salud.

No se atribuyen métricas, resultados o conclusiones específicas a esos trabajos
hasta contar con sus archivos fuente verificables.
