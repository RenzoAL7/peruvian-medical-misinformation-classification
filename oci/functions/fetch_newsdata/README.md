# `fetch-newsdata`

First OCI Function in the thesis pipeline. It reads the NewsData API key from
OCI Vault, requests Spanish health news country by country in a fixed order,
and writes one deduplicated CSV per run to the flat `bronze/` prefix in Object
Storage. The CSV follows the Bronze columns used by the thesis spreadsheet and
includes the publisher country.

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
NEWSDATA_TARGET_ROWS=100
NEWSDATA_COUNTRY_DELAY=2
NEWSDATA_PAGE_DELAY=4
NEWSDATA_MAX_RETRIES=2
NEWSDATA_REMOVEDUPLICATE=1
NEWSDATA_VIDEO=0
NEWSDATA_COUNTRY_SEQUENCE=ar,bo,cl,co,cr,cu,do,ec,es,gt,gq,hn,mx,ni,pa,pe,pr,py,sv,uy,ve
```

`NEWSDATA_QUERY` and `NEWSDATA_ENDPOINT` remain optional filters. The function
uses `NEWSDATA_COUNTRY_SEQUENCE` as an ordered list and makes one request per
country in that order during the same invocation. It appends new rows until
`NEWSDATA_TARGET_ROWS` is reached, then writes one CSV. Puerto Rico (`pr`) is
intentionally included as a separate territory. The order restarts at `ar` on
the next invocation; no cursor or state JSON is needed.

With `BRONZE_DEDUP_ENABLED=1`, each run reads prior CSVs under `bronze/` and
skips any `record_id` already stored there and also removes duplicates between
countries in the current run. This prevents the same canonical URL from
returning in multiple runs while the API's latest feed covers overlapping
48-hour windows. `NEWSDATA_MAX_PAGES=1` keeps the first pass to one request per
country; increase it only deliberately because each extra page is another API
request. `NEWSDATA_COUNTRY_DELAY` spaces country requests, while
`NEWSDATA_PAGE_DELAY` spaces pages within a country and
`NEWSDATA_MAX_RETRIES` retries temporary HTTP 429 responses. If fewer than the
target number of new articles exist in the available country pages, the CSV
contains the available rows rather than repeating old records. The default
query searches for common medical terms.

The function writes objects like:

```text
bronze/newsdata_batch_run_20261004T000000Z_ab12cd34.csv
```

The CSV columns are:

```text
record_id,source_name,canonical_url,published_at,title,
subtitle_or_bajada,topic,selection_status,retrieved_at,country
```

No API key is stored in the CSV. The Function must use a resource principal
with permission to read the Vault secret and create objects in `mednews-data`
whose name matches `bronze/*`.
