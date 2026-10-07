# `extract-news-body`

Second OCI Function in the thesis pipeline. It reads pending rows from the
flat `bronze/` prefix, downloads each article URL, extracts the main HTML text,
and writes one CSV batch under `silver/`.

The batch is row based rather than file based. Bronze objects are sorted by
their run name. The function consumes all pending rows in the first object
before continuing to the next one, and fills the configured batch when an
object contains fewer rows. For example, 23 pending rows in the first CSV and
27 in the second produce one 50-row Silver batch.

## OCI configuration

The function uses the same resource principal and Object Storage permissions as
`fetch-newsdata`:

```text
OBJECT_STORAGE_NAMESPACE=<tenancy Object Storage namespace>
OBJECT_STORAGE_BUCKET=mednews-data
BRONZE_PREFIX=bronze
SILVER_BODY_PREFIX=silver/body
BODY_BATCH_SIZE=50
BODY_MAX_SECONDS=150
BODY_TIME_BUFFER=10
BODY_REQUEST_TIMEOUT=15
BODY_MAX_RETRIES=1
BODY_MAX_BYTES=1500000
BODY_MIN_WORDS=150
BODY_MIN_CHARS=800
BODY_MAX_TEXT_CHARS=200000
```

`BODY_BATCH_SIZE` is a maximum. `BODY_MAX_SECONDS` leaves a safety margin below
the 300-second OCI Functions limit. If pages are slow, the function writes the
rows completed before the internal deadline and the remaining Bronze rows stay
pending for the next invocation.

The usual budget is 150 seconds with `BODY_TIME_BUFFER=10`; each URL has a
15-second request timeout and at most one retry. The elapsed time and pending
rows are visible in the invocation log. See the consolidated limits and
duration table in [`docs/limits_and_timing.md`](../../../docs/limits_and_timing.md).

The function reads all existing Silver CSVs and skips `record_id` values with a
terminal result. This prevents repeated requests to blocked or paywalled sites
while allowing timeouts, connection failures, throttling, and server errors to
retry on a later scheduled run. The output keeps every attempt with
`extraction_status` so the decision remains auditable.

## Silver output

Each invocation that processes at least one row writes:

```text
silver/body/body_run_20261005T000000Z_ab12cd34.csv
```

The output retains the Bronze columns and adds:

```text
body,http_status,extraction_method,extraction_status,
body_char_count,body_word_count,extracted_at,source_bronze_object,
extraction_run_id,extraction_error
```

`extraction_status` is `OK`, `CUERPO_INSUFICIENTE`, `HTTP_ERROR`, `TIMEOUT`,
`URL_ERROR`, or another explicit error status. A body is `OK` only when it has
at least 150 words and 800 characters, matching the project data schema. This
Function only extracts text; it never decides whether a claim is true or false.

## Manual invocation

```bash
oci fn function invoke \
  --function-id <extract-news-body-function-ocid> \
  --file - \
  --body '' \
  --region us-ashburn-1 \
  --read-timeout 360
```
