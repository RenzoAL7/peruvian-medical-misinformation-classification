# `extract-news-body`

Second OCI Function in the thesis pipeline. An Object Storage event identifies
one `bronze/*.csv` input object; the Function downloads the URLs in that file,
extracts the main HTML text, and writes exactly one corresponding CSV under
`silver/body/`. It never fills a run with pending rows from another Bronze
object.

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
BODY_MAX_REDIRECTS=5
BODY_MAX_BYTES=1500000
BODY_MIN_WORDS=150
BODY_MIN_CHARS=800
BODY_MAX_TEXT_CHARS=200000
```

`BODY_BATCH_SIZE` must accommodate the complete Bronze file (the Fetch Function
emits at most 50 rows). `BODY_MAX_SECONDS` leaves a safety margin below the
300-second OCI Functions limit. If pages are slow, the output still contains an
explicit `BODY_TIME_BUDGET` error row for every URL that could not be attempted.

The usual budget is 150 seconds with `BODY_TIME_BUFFER=10`; each URL has a
15-second request timeout and at most one retry. The elapsed time and pending
rows are visible in the invocation log. See the consolidated limits and
duration table in [`docs/limits_and_timing.md`](../../../docs/limits_and_timing.md).

The function follows up to five validated HTTP(S) redirects. It validates that
the incoming event belongs to the configured bucket and `bronze/` prefix, then
processes only that object's rows. Connection, HTTP, extraction, and time-budget
outcomes are persisted in the output CSV with `extraction_status`; they are not
silently retried during another run.

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
  --body '{"data":{"resourceName":"bronze/<input>.csv","additionalDetails":{"bucketName":"mednews-data"}}}' \
  --region us-ashburn-1 \
  --read-timeout 360
```
