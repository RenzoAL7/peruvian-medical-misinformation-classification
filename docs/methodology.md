# Metodología implementada en Seminario 1

## 1. Descubrimiento de candidatas

El Colab obtiene los `record_id` ya registrados en `Raw` y ejecuta el recolector del repositorio. La configuración solicita hasta tres candidatas de cada una de cuatro secciones textuales de salud: El Comercio, La República, Diario Correo y Diario Ojo.

Las cuatro fuentes se descubren desde páginas públicas permitidas por `robots.txt`, por lo que la corrida vigente no consume créditos de NewsData. Antes de conservar una URL se valida que pertenezca a la sección autorizada y que el título o bajada incluya un término médico y una señal de afirmación contrastable. La integración opcional con NewsData permanece limitada a cuatro solicitudes por corrida y excluye resultados de video.

Cada URL se normaliza y se transforma en un `record_id`. Las coincidencias con `Raw` se descartan durante la búsqueda. Antes de anexar, el Colab vuelve a leer la hoja y aplica una segunda deduplicación. Latina, El Peruano, Perú21 y RPP no se incluyen en la configuración vigente: las pruebas reales mostraron ruido temático, ausencia de resultados, restricciones de automatización o cuerpos demasiado breves.

## 2. Revisión humana en Raw

Las candidatas ingresan con estado `PENDIENTE`. El investigador determina si la noticia es médica, registra la razón y decide si contiene una afirmación médica concreta y contrastable. Campañas, anuncios administrativos, infraestructura, acceso a servicios y relatos sin una afirmación verificable se excluyen de la etapa de etiquetado.

## 3. Extracción del cuerpo

El Colab selecciona todas las filas con `is_medical=SI`, `is_claim_eligible=SI` y `review_status=COMPLETADA` que todavía no aparecen en `Extraccion`. Descarga la página con HTTPX, intenta extraer el texto con Trafilatura y usa BeautifulSoup como respaldo. El estado de extracción y el método quedan registrados.

## 4. Validación con evidencia

En `Extraccion`, el investigador delimita la afirmación principal y la contrasta con fuentes especializadas como MINSA, INS, EsSalud, OMS/OPS, PubMed u otra autoridad pertinente. Registra evidencia, justificación, etiqueta, revisor y estado de validación. Ni NewsData ni el medio periodístico determinan la etiqueta.

## 5. Alcance actual

El repositorio cubre adquisición, trazabilidad y deduplicación. El Colab cubre integración con Google Sheets y extracción del cuerpo. Todavía no se exporta automáticamente el corpus final ni se entrenan clasificadores; esas actividades corresponden a una etapa posterior, una vez cerrada la validación humana.
