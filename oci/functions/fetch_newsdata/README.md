# `fetch-newsdata`

First OCI Function in the thesis pipeline. It reads the NewsData API key from
OCI Vault, requests Spanish health news (without a country restriction by
default), and writes the original response plus run metadata to the Bronze
layer in Object Storage.

## Required function configuration

Set these application/function environment variables in OCI:

```text
NEWSDATA_SECRET_OCID=<OCID of the newsdata-api-key secret>
OBJECT_STORAGE_NAMESPACE=<tenancy Object Storage namespace>
OBJECT_STORAGE_BUCKET=mednews-data
BRONZE_PREFIX=bronze/newsdata
NEWSDATA_LANGUAGE=es
NEWSDATA_CATEGORY=health
```

Optional filters are `NEWSDATA_QUERY`, `NEWSDATA_COUNTRY`, and
`NEWSDATA_ENDPOINT`. The country variable is empty by default so the first
global Spanish-language run is not limited to Peru.

The function writes objects like:

```text
bronze/newsdata/2026/10/04/run_20261004T000000Z_ab12cd34.json
```

No API key is stored in this directory or in the JSON object. The Function
must use a resource principal with permission to read the Vault secret and
write objects in `mednews-data`.
