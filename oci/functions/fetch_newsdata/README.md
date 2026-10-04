# `fetch-newsdata`

First OCI Function in the thesis pipeline. It reads the NewsData API key from
OCI Vault, requests Spanish health news (without a country restriction by
default), and writes one CSV per run to the flat `bronze/` prefix in Object
Storage. The CSV follows the Bronze columns used by the thesis spreadsheet
and includes the publisher country.

## Required function configuration

Set these application/function environment variables in OCI:

```text
NEWSDATA_SECRET_OCID=<OCID of the newsdata-api-key secret>
OBJECT_STORAGE_NAMESPACE=<tenancy Object Storage namespace>
OBJECT_STORAGE_BUCKET=mednews-data
BRONZE_PREFIX=bronze
NEWSDATA_LANGUAGE=es
NEWSDATA_CATEGORY=health
NEWSDATA_SIZE=10
NEWSDATA_REMOVEDUPLICATE=1
NEWSDATA_VIDEO=0
```

Optional filters are `NEWSDATA_QUERY`, `NEWSDATA_COUNTRY`, and
`NEWSDATA_ENDPOINT`. The default query searches for common medical terms. The
country variable is empty by default so a global Spanish-language run is not
limited to Peru.

The function writes objects like:

```text
bronze/newsdata_run_20261004T000000Z_ab12cd34.csv
```

The CSV columns are:

```text
record_id,source_name,canonical_url,published_at,title,
subtitle_or_bajada,topic,selection_status,retrieved_at,country
```

No API key is stored in the CSV. The Function must use a resource principal
with permission to read the Vault secret and create objects in `mednews-data`
whose name matches `bronze/*`.
