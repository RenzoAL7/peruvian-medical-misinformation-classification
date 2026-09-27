# Corpus de noticias médicas peruanas

Este repositorio implementa la primera parte de Seminario 1: descubrir un batch trazable de noticias candidatas y preparar su revisión humana. Aún no entrena modelos ni asigna etiquetas automáticamente.

El batch actual solicita 60 candidatas: 10 por medio para El Comercio, RPP Noticias, Latina Noticias, El Peruano, Perú21 y La República. NewsData.io solo aporta metadatos de descubrimiento: URL, título, bajada disponible, fecha, autor y fuente. Que una URL provenga de uno de esos medios no determina que sea médica, verdadera ni falsa.

## Flujo activo

    NewsData.io (60 candidatas, 10 por fuente)
      -> CSV de URLs y títulos por corrida
      -> CSV de revisión manual
      -> relevancia médica, cuerpo y evidencia completados por el investigador
      -> CSV binario real para entrenamiento futuro

1. El batch filtra por fuente, español, Perú, categoría health y términos médicos configurados. La API de noticias recientes trabaja con una ventana de hasta 48 horas. Si una fuente no tiene suficientes resultados, el reporte registra el faltante y nunca inventa URLs.
2. En la hoja manual, el investigador marca is_medical=SI o NO. Para las noticias médicas, pega el cuerpo, delimita la afirmación principal y registra su evidencia. La etiqueta es manual: 0, 1 o EXCLUIDA.
3. Solo una fila médica con revisión COMPLETADA, cuerpo, afirmación, justificación y fuente/URL de evidencia puede pasar al CSV binario. Las filas EXCLUIDA, no médicas y duplicadas no ingresan al entrenamiento.

No se ejecuta scraping de artículos, extracción con LLM, verificación automática ni generación sintética en este batch. Esas decisiones requieren un protocolo adicional y no reemplazan la revisión humana.

## Instalación

    python3 -m venv .venv
    .venv/bin/python -m pip install -e '.[dev]'
    .venv/bin/python -m pytest -q

La clave se conserva localmente en .env y nunca se sube al repositorio:

    cp .env.example .env
    # editar .env y definir NEWSDATA_API_KEY

## Ejecutar una corrida de 60 candidatas

Primero valida la configuración sin consumir la API:

    .venv/bin/python scripts/01_collect_newsdata_urls.py --dry-run

Luego ejecuta el batch. El identificador permite distinguir corridas:

    .venv/bin/python scripts/01_collect_newsdata_urls.py --run-id batch_60_20260927

La corrida crea dos archivos locales:

    data/raw/source_url_runs/batch_60_20260927.csv
    reports/newsdata_runs/batch_60_20260927.json

El CSV contiene una fila por candidata y el JSON explica el conteo por fuente, faltantes y errores. La configuración reserva un máximo de 28 consultas por corrida para respetar el límite de la API. Si NewsData responde 429, el script se detiene en vez de insistir y deja el reporte listo para ejecutar una nueva corrida después del reinicio del proveedor. Los resultados se guardan en el repositorio local, pero se ignoran por Git para evitar mezclar corridas, datos de trabajo y credenciales en el código.

Para completar un batch parcial después del reinicio de la cuota, conserva sus candidatas y solicita solo los faltantes. Usa un nuevo identificador de corrida:

    .venv/bin/python scripts/01_collect_newsdata_urls.py \
      --run-id batch_60_20260927_r2 \
      --resume-from data/raw/source_url_runs/batch_60_20260927.csv

## Revisión manual y exportación final

Convierte una corrida de candidatas en una hoja de trabajo que se puede abrir en Excel, manteniéndola como CSV UTF-8 al guardar:

    .venv/bin/python scripts/02_create_manual_review.py \
      --input data/raw/source_url_runs/batch_60_20260927.csv

Completa, como mínimo, estas columnas para cada fila médica que se etiquete:

    is_medical=SI
    body
    main_medical_claim
    evidence_source
    evidence_url
    label (0, 1 o EXCLUIDA)
    label_reason
    review_status=COMPLETADA

Después exporta solo las noticias reales con etiqueta binaria:

    .venv/bin/python scripts/03_export_training_csv.py \
      --input data/review/batch_60_20260927_manual_review.csv

El resultado es data/processed/training_corpus_real.csv. Su texto de entrada es title + subtitle_or_bajada + body. URL, fuente, fecha, autor y evidencia permanecen como metadatos y no se usan como variables del modelo.

## Límites metodológicos

La API no valida el contenido de una noticia. El investigador decide primero si el caso pertenece a salud/medicina y después contrasta la afirmación con una fuente oficial o científica que registra en la hoja. La fuente periodística no determina la etiqueta. La deduplicación, el balance de clases y la división estratificada 70/15/15 ocurrirán después de finalizar la revisión humana.

La documentación de [NewsData.io sobre el endpoint Latest](https://newsdata.io/blog/latest-news-endpoint/) describe la ventana reciente y los filtros de dominio, idioma, país, categoría y consulta usados por esta configuración. La cuota gratuita documentada de 30 créditos por 15 minutos explica la detención segura ante 429 en [la guía de límites de NewsData](https://newsdata.io/blog/newsdata-rate-limit/). Consulta el [esquema de datos](docs/data_schema.md) y la [metodología](docs/methodology.md) antes de modificar el protocolo.
