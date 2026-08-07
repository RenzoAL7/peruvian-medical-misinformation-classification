# Datos

Esta carpeta organiza los datos según su etapa de procesamiento.

- `raw/`: archivos recibidos sin modificación. No se suben a Git.
- `interim/`: salidas temporales de auditoría y limpieza. No se suben a Git.
- `processed/`: conjuntos listos para modelado. No se suben a Git mientras contengan datos derivados sujetos a permisos.
- `qrels/`: especificación y futuros archivos con juicios de relevancia entre consultas y documentos candidatos.

El archivo fuente debe conservarse con un nombre estable y anotarse en el diccionario de datos. No se deben combinar automáticamente las hojas auxiliares con la hoja maestra sin una revisión de solapamientos.
