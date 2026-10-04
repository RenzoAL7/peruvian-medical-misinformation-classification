# `fetch-newsdata`

First OCI Function in the thesis pipeline. It reads the NewsData API key from
OCI Vault, requests Spanish health news for one country per invocation, and
writes one CSV per run to the flat `bronze/` prefix in Object Storage. The CSV
follows the Bronze columns used by the thesis spreadsheet and includes the
publisher country.

## Required function configuration

Set these application/function environment variables in OCI:

```text
NEWSDATA_SECRET_OCID=<OCID of the newsdata-api-key secret>
OBJECT_STORAGE_NAMESPACE=<tenancy Object Storage namespace>
OBJECT_STORAGE_BUCKET=mednews-data
BRONZE_PREFIX=bronze
BRONZE_DEDUP_ENABLED=1
NEWSDATA_LANGUAGE=es
NEWSDATA_CATEGORY=health
NEWSDATA_SIZE=10
NEWSDATA_MAX_PAGES=1
NEWSDATA_PAGE_DELAY=4
NEWSDATA_MAX_RETRIES=2
NEWSDATA_REMOVEDUPLICATE=1
NEWSDATA_VIDEO=0
NEWSDATA_COUNTRY_SEQUENCE=ar,bo,cl,co,cr,cu,do,ec,es,gt,gq,hn,mx,ni,pa,pe,pr,py,sv,uy,ve
```

`NEWSDATA_QUERY` and `NEWSDATA_ENDPOINT` remain optional filters. The function
uses `NEWSDATA_COUNTRY_SEQUENCE` as an ordered cycle and selects exactly one
country per invocation. Puerto Rico (`pr`) is intentionally included as a
separate territory. After the CSV is written, the cursor is stored as
`bronze/newsdata_coverage_state.json` with the next country, cycle, and last
run. A failed invocation does not advance the cursor. Setting
`NEWSDATA_COUNTRY` temporarily overrides the automatic cursor for a manual
country run.

With `BRONZE_DEDUP_ENABLED=1`, each run reads prior CSVs under `bronze/` and
skips any `record_id` already stored there. This prevents the same canonical
URL from returning in multiple runs while the API's latest feed covers
overlapping 48-hour windows. `NEWSDATA_MAX_PAGES=1` keeps the country cycle to
one request per country; increase it only deliberately because each extra
page is another API request. `NEWSDATA_PAGE_DELAY` spaces requests to respect
the provider rate limit, while `NEWSDATA_MAX_RETRIES` retries temporary HTTP
429 responses. The default query searches for common medical terms.

The function writes objects like:

```text
bronze/newsdata_run_20261004T000000Z_ab12cd34.csv
```

Automatic country runs use the country in the object name:

```text
bronze/newsdata_ar_run_20261004T000000Z_ab12cd34.csv
```

The CSV columns are:

```text
record_id,source_name,canonical_url,published_at,title,
subtitle_or_bajada,topic,selection_status,retrieved_at,country
```

No API key is stored in the CSV. The Function must use a resource principal
with permission to read the Vault secret and create objects in `mednews-data`
whose name matches `bronze/*`.
