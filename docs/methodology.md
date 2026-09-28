# Metodología implementada en Seminario 1

## 1. Descubrimiento de candidatas

El Colab obtiene los `record_id` ya registrados en `Raw` y ejecuta el recolector del repositorio. La configuración solicita hasta dos candidatas de cada uno de seis medios peruanos: El Comercio, RPP Noticias, Latina Noticias, El Peruano, Perú21 y La República.

Latina y Perú21 se procesan primero mediante sus archivos públicos. Los demás medios usan el endpoint `latest` de NewsData con idioma español, país Perú y categoría `health`. Para aprovechar cada crédito, dos consultas prioritarias agrupan con `OR` los diez términos médicos. Si todavía faltan candidatas, se prueban términos individuales, cuyo orden rota según la cantidad de identificadores ya registrados. Las consultas se reparten por rondas entre los medios pendientes y se detienen con un límite interno de 30 solicitudes.

Cada URL se normaliza y se transforma en un `record_id`. Las coincidencias con `Raw` se descartan durante la búsqueda. Antes de anexar, el Colab vuelve a leer la hoja y aplica una segunda deduplicación.

## 2. Revisión humana en Raw

Las candidatas ingresan con estado `PENDIENTE`. El investigador determina si la noticia es médica, registra la razón y decide si contiene una afirmación médica concreta y contrastable. Campañas, anuncios administrativos, infraestructura, acceso a servicios y relatos sin una afirmación verificable se excluyen de la etapa de etiquetado.

## 3. Extracción del cuerpo

El Colab selecciona todas las filas con `is_medical=SI`, `is_claim_eligible=SI` y `review_status=COMPLETADA` que todavía no aparecen en `Extraccion`. Descarga la página con HTTPX, intenta extraer el texto con Trafilatura y usa BeautifulSoup como respaldo. El estado de extracción y el método quedan registrados.

## 4. Validación con evidencia

En `Extraccion`, el investigador delimita la afirmación principal y la contrasta con fuentes especializadas como MINSA, INS, EsSalud, OMS/OPS, PubMed u otra autoridad pertinente. Registra evidencia, justificación, etiqueta, revisor y estado de validación. Ni NewsData ni el medio periodístico determinan la etiqueta.

## 5. Alcance actual

El repositorio cubre adquisición, trazabilidad y deduplicación. El Colab cubre integración con Google Sheets y extracción del cuerpo. Todavía no se exporta automáticamente el corpus final ni se entrenan clasificadores; esas actividades corresponden a una etapa posterior, una vez cerrada la validación humana.
