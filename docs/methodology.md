# Metodología implementada en Seminario 1

## 1. Descubrimiento de candidatas

El Colab obtiene los `record_id` ya registrados en `Raw` y ejecuta el recolector del repositorio. La configuración busca una meta global de 12 candidatas en El Comercio, La República, Diario Correo, Diario Ojo, MINSA, Gestión, El Popular y Canal N. Cada fuente puede aportar como máximo dos candidatas.

Las fuentes se descubren desde páginas públicas permitidas por `robots.txt`, por lo que la corrida vigente no consume créditos de NewsData. Antes de conservar una URL se valida que pertenezca al medio autorizado y que el título o bajada incluya un término médico y una señal de afirmación contrastable. La selección final rota el primer medio según la cantidad de registros existentes y toma una noticia por fuente en cada ronda. La integración opcional con NewsData permanece limitada a cuatro solicitudes por corrida, excluye resultados de video y se detiene al alcanzar la meta global.

Cada URL se normaliza y se transforma en un `record_id`. Las coincidencias con `Raw` se descartan durante la búsqueda. Antes de anexar, el Colab vuelve a leer la hoja y aplica una segunda deduplicación. La ampliación no significa aceptar cualquier nota: los medios o formatos que no permiten automatización, devuelven videos o producen cuerpos insuficientes permanecen fuera hasta que una nueva prueba documentada justifique incorporarlos.

## 2. Revisión humana en Raw

Las candidatas ingresan con estado `PENDIENTE`. El investigador determina si la noticia es médica, registra la razón y decide si contiene una afirmación médica concreta y contrastable. Campañas, anuncios administrativos, infraestructura, acceso a servicios y relatos sin una afirmación verificable se excluyen de la etapa de etiquetado.

## 3. Extracción del cuerpo

El Colab selecciona todas las filas con `is_medical=SI`, `is_claim_eligible=SI` y `review_status=COMPLETADA` que todavía no aparecen en `Extraccion`. Descarga la página con HTTPX, intenta extraer el texto con Trafilatura y usa BeautifulSoup como respaldo. El estado de extracción y el método quedan registrados.

## 4. Validación con evidencia

En `Extraccion`, el investigador delimita la afirmación principal y la contrasta con fuentes especializadas como MINSA, INS, EsSalud, OMS/OPS, PubMed u otra autoridad pertinente. Registra evidencia, justificación, etiqueta, revisor y estado de validación. Ni NewsData ni el medio periodístico determinan la etiqueta. Cuando la candidata proviene de MINSA, la evidencia confirmatoria debe registrarse con una función independiente y no asumirse a partir del dominio.

## 5. Alcance actual

El repositorio cubre adquisición, trazabilidad y deduplicación. El Colab cubre integración con Google Sheets y extracción del cuerpo. Todavía no se exporta automáticamente el corpus final ni se entrenan clasificadores; esas actividades corresponden a una etapa posterior, una vez cerrada la validación humana.
