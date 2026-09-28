# Datos temporales

El Colab y el recolector pueden crear dos tipos de archivos locales:

```text
data/00_control/run_registry.csv
data/01_candidates/<run_id>.csv
```

El primero registra el resultado de las corridas locales. El segundo contiene las candidatas que el Colab anexará a `Raw`. Ambos están ignorados por Git; la fuente de trabajo compartida es Google Sheets.
