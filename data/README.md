# Organización de datos del núcleo

La adaptación del dataset es la parte principal pendiente de Seminario 1.

- `raw/`: archivo original sin modificaciones. No se sube a Git.
- `interim/`: auditorías, normalización y resultados temporales. No se sube a Git.
- `processed/`: `Claims` y `Evidence` preparados para recuperación. No se sube a Git mientras contenga datos derivados sujetos a permisos.
- `qrels/`: juicios de relevancia y tripletas revisadas; su esquema está documentado en `data/qrels/README.md`.

El archivo fuente debe conservar su versión, fecha de obtención y hoja de origen.
Para `FakeNewsEspañol2024`, la hoja maestra se revisa primero y no se combinan
automáticamente hojas auxiliares.

Las etiquetas `VERDADERO/FALSO` se conservan como metadatos del registro
original. No se transforman automáticamente en relevancia de recuperación. La
URL, la fuente y el texto de evidencia deben conservar su procedencia y estado
de extracción.
