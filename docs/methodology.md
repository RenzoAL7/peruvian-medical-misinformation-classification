# Metodología de Seminario 1

## Alcance

La primera entrega construye un flujo reproducible para reunir y revisar noticias peruanas candidatas. La unidad inicial es una URL pública con título y metadatos; una fila solo se transforma en ejemplo de entrenamiento después de la revisión manual. No se entrena ningún clasificador en esta fase.

## Adquisición por lotes

La configuración configs/batch_12.yaml define un batch de 12 candidatas: 2 por cada uno de seis medios peruanos (elcomercio.pe, rpp.pe, latinanoticias.pe, elperuano.pe, peru21.pe y larepublica.pe). El script consulta el endpoint latest de NewsData.io con filtros de dominio, idioma español, país Perú, categoría de salud y términos médicos en español. Conserva el identificador de corrida, consulta, fecha de recuperación, URL original y URL canónica. La API puede devolver menos de dos resultados para una fuente durante su ventana reciente; el sistema registra el faltante y no lo rellena con URLs de otro medio ni con datos fabricados.

La corrida limita sus solicitudes totales y se detiene ante una respuesta 429. Esto respeta la cuota del proveedor y evita insistir sobre un límite temporal. Cuando una corrida queda parcial, el parámetro --resume-from conserva sus URLs válidas, marca su run_id de origen y solicita únicamente las candidatas faltantes en una ejecución posterior.

La API se usa solo para descubrimiento. En particular, el batch no extrae el cuerpo de cada página, no infiere que una noticia sea médica por el sitio donde se publicó y no asigna etiquetas de veracidad. Esta separación evita que la fuente periodística o la clasificación comercial de la API se conviertan en una señal indebida del modelo posterior.

## Revisión humana y etiquetado

Después de cada corrida, 02_create_manual_review.py genera una hoja CSV. El investigador primero decide si la candidata trata salud o medicina. Las filas NO se conservan como descarte temático. Para una fila SI, el investigador agrega el cuerpo, delimita una afirmación médica principal y busca evidencia adecuada, por ejemplo en MINSA, INS, EsSalud, OMS/OPS o PubMed. Luego registra la fuente, URL, fragmento, justificación y una etiqueta manual: 0 si la afirmación es compatible con la evidencia, 1 si está contradicha, o EXCLUIDA si no puede verificarse, es ambigua o no permite aislar una sola afirmación.

La etiqueta no la produce un LLM ni se deduce del medio. 03_export_training_csv.py solo acepta filas médicas completadas, con evidencia documentada y etiqueta binaria. Además normaliza Unicode NFKC, espacios y el texto title + subtitle_or_bajada + body, y elimina duplicados exactos por URL canónica o contenido. Evidencia, autor, fecha, URL y fuente quedan como metadatos, no como características de entrada.

## Preparación posterior

El balance de clases se evaluará únicamente después de terminar la revisión y deduplicación de noticias reales. Cualquier generación sintética, si se aprueba en una fase posterior, se documentará de forma separada, se marcará con is_synthetic=true y no deberá incorporarse en validación ni prueba. Después se dividirán solo los registros reales con etiquetas 0 y 1 en 70 % entrenamiento, 15 % validación y 15 % prueba, conservando el conjunto de prueba para evaluación final.

La siguiente etapa comparará TF-IDF con Naive Bayes, Regresión Logística y SVM lineal; GloVe con BiLSTM; Word2Vec con LSTM; y BERT, BETO y RoBERTa-BNE. Las métricas se calcularán una vez cerrado el corpus, sin usar los metadatos de procedencia para predecir la etiqueta.
