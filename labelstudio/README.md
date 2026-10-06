# Revisión humana con Label Studio

Label Studio es la última revisión humana del pipeline. `silver/evidence/` no
es todavía Gold: contiene candidatos recuperados de PubMed y puntuaciones de
similitud. Una persona debe decidir la relación de la evidencia y la etiqueta
final antes de que una fila entre al conjunto de entrenamiento.

## 1. Ejecutar Label Studio

Con Docker Desktop iniciado:

```bash
docker run -d --name mednews-labelstudio \
  -p 8080:8080 \
  -v "$PWD/labelstudio-data:/label-studio/data" \
  heartexlabs/label-studio:latest
```

Abre `http://localhost:8080`, crea una cuenta local y un proyecto. En la
configuración del proyecto copia el contenido de [`config.xml`](config.xml).
El proyecto usado durante la prueba fue `MedNews LATAM - Evidence Review`
(id 1); para un conjunto limpio se puede crear otro proyecto y pasar su id a
los scripts.

## 2. Importar evidencia sin duplicar

Guarda uno o varios CSV de `silver/evidence/` en una carpeta local y ejecuta:

```bash
export LABEL_STUDIO_TOKEN='token-local-de-label-studio'
python3 labelstudio/import_evidence.py \
  --project-id 1 \
  --input /ruta/a/evidence_1.csv /ruta/a/evidence_2.csv \
  --manifest /ruta/privada/labelstudio-manifest.csv
```

El script conserva la fila más reciente por `record_id`, ignora estados que no
sean `OK`, consulta las tareas que ya existen en el proyecto y solo importa
registros nuevos. Se puede ejecutar después de cada corrida de evidence. No
guardes el token, las API keys ni el manifest con datos en Git.

## 3. Anotar

Para cada tarea compara el claim en español con los abstracts, marca
`supports`, `contradicts` o `unclear`, marca `RESPALDADA`, `REFUTADA`,
`NO_DETERMINABLE` o `EXCLUIDA`, y escribe una justificación verificable.
`EXCLUIDA` y `NO_DETERMINABLE` se conservan para auditoría, pero no entran al
Gold binario de entrenamiento. La decisión humana prevalece sobre la
puntuación de embedding.

## 4. Exportar las etiquetas

```bash
python3 labelstudio/export_annotations.py \
  --project-id 1 \
  --output /ruta/privada/gold_labels.csv \
  --raw-export /ruta/privada/labelstudio-export.json
```

El exportador toma la anotación completada más reciente por `record_id` y
produce una fila Gold por noticia. El control `final_label` de la interfaz se
exporta como la columna canónica `label`. El CSV resultante debe revisarse
antes de generar el split 70/15/15. `annotation_id` permite volver a la tarea
exacta.

## Cuándo importar y cuánto demora

La importación se puede ejecutar después de cada CSV de evidence o en lotes
diarios. No depende de los cron de OCI: Label Studio es la etapa humana y no
tiene el timeout síncrono de una Function. El manifest local y la consulta del
`record_id` existente hacen que volver a ejecutar el comando sea seguro. Una
fila que todavía no esté en estado `OK` se deja fuera hasta que evidence la
complete en una corrida posterior. Los tiempos de las Functions, el drenaje
horario y los límites de PubMed/Gemini/Embed están en
[`docs/limits_and_timing.md`](../docs/limits_and_timing.md).

## Trabajo entre dos personas

Para colaborar en la misma instancia, el dueño del proyecto invita al otro
usuario desde **Members** y ambos usan el mismo `project_id`. Cada importación
se deduplica por `record_id`; las reimportaciones no crean una segunda tarea.
Si se necesita doble anotación, se activa la segunda anotación sobre la misma
tarea y se resuelve el desacuerdo antes de exportar.

```text
silver/evidence/*.csv
        |
        | import_evidence.py (dedupe record_id)
        v
Label Studio: relación + etiqueta + nota humana
        |
        | export_annotations.py (última anotación por record_id)
        v
gold_labels.csv -> revisión final -> dataset de entrenamiento
```
