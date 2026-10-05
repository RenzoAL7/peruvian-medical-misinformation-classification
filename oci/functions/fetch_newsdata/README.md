# `fetch-newsdata`

First OCI Function in the thesis pipeline. It reads the NewsData API key from
OCI Vault, requests Spanish health news country by country in a fixed order,
and writes one deduplicated CSV per run to the flat `bronze/` prefix in Object
Storage. The CSV follows the Bronze columns used by the thesis spreadsheet and
includes the publisher country. It can rotate across multiple Vault secrets so
one exhausted or unavailable NewsData key does not stop the batch.

## Required function configuration

Set these application/function environment variables in OCI:

```text
NEWSDATA_SECRET_OCIDS=<OCID of key 1>,<OCID of key 2>
# NEWSDATA_SECRET_OCID remains supported when only one key is configured.
OBJECT_STORAGE_NAMESPACE=<tenancy Object Storage namespace>
OBJECT_STORAGE_BUCKET=mednews-data
BRONZE_PREFIX=bronze
BRONZE_DEDUP_ENABLED=1
NEWSDATA_LANGUAGE=es
NEWSDATA_CATEGORY=health
NEWSDATA_SIZE=10
NEWSDATA_MAX_PAGES=8
NEWSDATA_TARGET_ROWS=100
NEWSDATA_REQUIRE_TARGET_ROWS=0
NEWSDATA_COUNTRY_GROUP_SIZE=5
NEWSDATA_COUNTRY_DELAY=1
NEWSDATA_PAGE_DELAY=1
NEWSDATA_MAX_RETRIES=2
NEWSDATA_REMOVEDUPLICATE=1
NEWSDATA_VIDEO=0
NEWSDATA_COUNTRY_SEQUENCE=ar,bo,cl,co,cr,cu,do,ec,es,gt,gq,hn,mx,ni,pa,pe,pr,py,sv,uy,ve
NEWSDATA_QUERY=(salud OR medicina OR médico OR enfermedad OR vacuna OR tratamiento OR fármaco OR cáncer OR diabetes)
```

`NEWSDATA_QUERY` and `NEWSDATA_ENDPOINT` remain optional filters. The function
splits `NEWSDATA_COUNTRY_SEQUENCE` into groups of up to five countries (the
NewsData limit), requests each group in order, and sorts the resulting rows
back into the configured country order before writing the CSV. It appends new
rows until `NEWSDATA_TARGET_ROWS` is reached. Puerto Rico (`pr`) is
intentionally included as a separate territory. The order restarts at `ar` on
the next invocation; no cursor or state JSON is needed.

The default medical query includes general terms such as `salud`, `médico`,
`medicina`, `enfermedad`, and `hospital` in addition to specific terms such as
`cáncer`, `diabetes`, `vacuna`, and `tratamiento`.

With `BRONZE_DEDUP_ENABLED=1`, each run reads prior CSVs under `bronze/` and
skips any `record_id` already stored there and also removes duplicates between
countries in the current run. This prevents the same canonical URL from
returning in multiple runs while the API's latest feed covers overlapping
48-hour windows. `NEWSDATA_MAX_PAGES` controls pages per country group;
`NEWSDATA_COUNTRY_GROUP_SIZE=5` and eight pages mean at most 40 API requests
for a full 21-country pass. When two Vault keys are configured, groups use the
keys in round-robin order and fail over to another key if a request fails.
Each extra page is another API credit. `NEWSDATA_COUNTRY_DELAY` spaces country
group requests, while `NEWSDATA_PAGE_DELAY` spaces pages within a country group
and `NEWSDATA_MAX_RETRIES` retries temporary HTTP 429 responses. With
`NEWSDATA_REQUIRE_TARGET_ROWS=0` writes the available new rows even when the
batch has fewer than 100; set it to `1` only when an incomplete CSV must be
rejected. The query broadens the medical vocabulary and must remain at most
100 characters because that is the NewsData API limit.

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
with permission to read every Vault secret listed in `NEWSDATA_SECRET_OCIDS`
and create objects in `mednews-data` whose name matches `bronze/*`.
