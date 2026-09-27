# Corpus de noticias médicas peruanas

Este repositorio implementa la adquisición y preparación manual del corpus para Seminario 1. No entrena modelos ni etiqueta automáticamente una noticia como verdadera o falsa.

## Qué hace cada corrida

Cada corrida busca hasta 12 candidatas: 2 de cada medio.

1. El Comercio
2. RPP Noticias
3. Latina Noticias
4. El Peruano
5. Perú21
6. La República

NewsData.io entrega metadatos de descubrimiento para las fuentes que cubre. Latina Noticias se descubre directamente desde sus archivos públicos de [Salud](https://latinanoticias.pe/noticias-sobre/salud/) y [Medicina](https://latinanoticias.pe/noticias-sobre/medicina/); Perú21 usa su archivo público de [Salud](https://peru21.pe/noticias/salud/). En ambas fuentes, NewsData queda configurado como respaldo si los archivos públicos no alcanzan las dos URLs. Las palabras clave solo filtran candidatas para evitar menú, publicidad y notas ajenas; la revisión manual sigue decidiendo si una noticia es médica y su etiqueta. El medio no determina si la noticia es médica ni cuál será su etiqueta.

## Carpetas

    configs/
      batch_12.yaml             configuración del batch

    data/
      00_control/               contador e historial de corridas
      01_candidates/            URLs y títulos obtenidos por la API
      02_review/                CSV para completar manualmente en Excel
      03_processed/             corpus binario real listo para entrenar

    reports/
      runs/                     resumen JSON por corrida

    scripts/
      00_show_run_history.py    muestra el contador
      01_collect_newsdata_urls.py
      02_create_manual_review.py
      03_export_training_csv.py

Los CSV generados, reportes y la clave API se guardan localmente y están ignorados por Git.

## Pasos para obtener datos de la API

### 1. Instalar

    make setup

### 2. Configurar la clave

    cp .env.example .env

Abre .env y escribe la clave en NEWSDATA_API_KEY. No subas ese archivo a Git.

### 3. Ver el contador de corridas

    make history

### 4. Verificar el batch sin usar la API

    make plan

Debe indicar: 12 candidatas = 2 por cada una de 6 fuentes.

### 5. Ejecutar una corrida real

    make run

El script crea automáticamente un identificador como run_002_20260927T.... El número aumenta una vez por cada ejecución real y se registra en data/00_control/run_registry.csv.

La salida queda en:

    data/01_candidates/<run_id>.csv
    reports/runs/<run_id>.json

Si una fuente no tiene resultados recientes o NewsData limita temporalmente la cuenta, la corrida queda parcial y el JSON lo documenta. Para Latina, el archivo público se consulta sin paginación, pues `robots.txt` bloquea rutas `/page/`. Nunca se inventan URLs.

### 6. Crear la hoja de revisión manual

Reemplaza <run_id> por el nombre generado en el paso anterior.

    make review RUN_ID=<run_id>

Completa en Excel y guarda como CSV UTF-8:

    is_medical
    is_claim_eligible
    body
    main_medical_claim
    evidence_source
    evidence_url
    label
    label_reason
    review_status

### 7. Exportar el corpus real binario

    make export REVIEW=data/02_review/<run_id>_manual_review.csv

El resultado queda en data/03_processed/training_corpus_real.csv. Solo exporta filas médicas con una afirmación verificable (`is_claim_eligible=SI`), completadas, con evidencia documentada y etiqueta 0 o 1. Las notas administrativas, campañas, acceso a servicios o casos sociales se marcan `is_claim_eligible=NO` y no ingresan al corpus. El batch compartido vigente está descrito en `data/README.md`.

## Límites del flujo

La API descubre candidatas; la persona investigadora decide si la noticia es médica y registra la evidencia que respalda la etiqueta 0, 1 o EXCLUIDA. La fuente, URL, fecha y autor se conservan para trazabilidad, pero no son variables de entrada del modelo.

Para retomar una corrida parcial después de que NewsData restablezca su cuota:

    make resume FROM=data/01_candidates/<run_id_anterior>.csv

El nuevo archivo conserva las candidatas previas y busca solo los faltantes por medio.

Para ver todos los comandos disponibles:

    make help
