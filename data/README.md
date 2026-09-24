# Organización de datos

El dataset de entrenamiento se construye a partir de noticias médicas en
español recolectadas desde El Comercio, RPP Noticias y Latina Noticias.

```text
data/
├── raw/          # manifiesto local y noticias extraídas; no versionado
├── annotations/  # etiquetas y evidencia; no versionado
├── interim/      # auditorías y transformaciones temporales
├── processed/    # dataset binario final para el entrenamiento
└── source_urls.example.csv
```

El archivo original de cada fuente no se modifica. Los registros descargados y
los textos derivados permanecen en rutas ignoradas por Git. La plantilla de
URLs sí se versiona, pero no debe incluir claves, cookies ni contenido privado.

La etiqueta final solo puede ser `REAL` o `FAKE`. Los casos ambiguos no entran
al dataset final y deben quedar explicados en la anotación o auditoría.

El texto de la noticia es la entrada del modelo. Las referencias de PubMed,
fuentes oficiales, URLs y notas de los anotadores se conservan para justificar
la etiqueta, no para filtrar la predicción durante el entrenamiento.
