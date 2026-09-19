# Notebooks del núcleo

Por ahora se mantiene un único notebook ejecutable. Los notebooks de auditoría,
qrels y experimentos con datos reales se agregarán cuando el dataset adaptado
esté definido.

## Minisimulación local de Seminario 1

El notebook `00_minisimulacion_query_coseno.ipynb` demuestra el recorrido
completo de una query de prueba hasta el ranking. Usa un corpus sintético y
contiene cuatro enfoques: TF-IDF, BM25, SBERT preentrenado y SBERT ajustado con
Triplet Loss. No requiere el dataset real, APIs externas ni RAG para la parte
principal.

Desde la raíz del repositorio, crea y activa el entorno con:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e .
.venv/bin/python -m ipykernel install --user \
  --name recomendador-fuentes-confiables \
  --display-name "Python (recomendador-fuentes-confiables)"
```

Luego abre JupyterLab:

```bash
.venv/bin/jupyter lab
```

En VS Code también se puede seleccionar directamente el intérprete
`.venv/bin/python` como kernel del notebook.

SBERT real es opcional porque requiere descargar dependencias y un modelo
multilingüe. El ajuste con Triplet Loss también usa `datasets` y `accelerate`,
dependencias requeridas por `SentenceTransformer.fit` en versiones recientes.
Para habilitar esa sección del notebook:

```bash
.venv/bin/python -m pip install -e '.[sbert]'
```

Después selecciona el kernel `.venv/bin/python`, cambia `RUN_REAL_SBERT = True`
en la sección comparativa y ejecuta nuevamente las celdas desde el inicio.
