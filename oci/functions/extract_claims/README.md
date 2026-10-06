# `extract-claims`

Third OCI Function in the thesis pipeline. It reads the article bodies already
written under `silver/body/`, skips rows without a body and rows whose body
extraction status is not `OK`, and extracts a candidate medical claim with
either OCI Generative AI or the public Gemini API. For Google Gemini, one
request analyzes several articles and returns one validated JSON item per
`record_id`, reducing API calls and rate-limit pressure. The Google API key is
read at invocation time from OCI Vault and is never stored in the image or
repo.

The model is used only to structure the article into a candidate claim and to
prepare a faithful English rendering plus a PubMed search query. It does not
decide whether the claim is true or false. Human review and evidence are
required later.

## Configuration

```text
OBJECT_STORAGE_NAMESPACE=idur1kkrru56
OBJECT_STORAGE_BUCKET=mednews-data
SILVER_BODY_PREFIX=silver/body
SILVER_CLAIMS_PREFIX=silver/claims
LLM_MODEL_ID=google.gemini-2.5-flash
LLM_REGION=us-ashburn-1
GENAI_COMPARTMENT_ID=<Cloud compartment OCID>
LLM_BATCH_SIZE=10
LLM_REQUEST_BATCH_SIZE=10
LLM_MAX_SECONDS=240
LLM_TIME_BUFFER=10
LLM_MAX_BODY_CHARS=12000
LLM_MAX_TOKENS=3000
LLM_REQUEST_TIMEOUT=30
LLM_TEMPERATURE=0.0
LLM_TOP_P=0.9
LLM_MAX_RETRIES=0
```

When OCI Generative AI model quota is unavailable, use the Google provider:

```text
LLM_PROVIDER=google
LLM_MODEL_ID=gemini-3.5-flash-lite
GOOGLE_GEMINI_SECRET_OCIDS=<OCI Vault secret OCID API 1>,<OCI Vault secret OCID API 2>
# GOOGLE_GEMINI_SECRET_OCID remains supported for one key.
```

Each secret must contain one Gemini API key as plain text. The Function reads
both secrets at invocation time, rotates them round-robin and fails over to the
other project on quota, authentication, or rate-limit errors. The dynamic
group must be allowed to read both secrets. The request uses the
`generateContent` endpoint and sends the key in the `x-goog-api-key` header.
`llm_key_slot` records which loaded slot produced each row without exposing the
key.

The batch is filled across all CSVs in `silver/body/`, in deterministic object
name order. Record IDs already present in `silver/claims/` are skipped, so a
second invocation continues with new rows. `LLM_BATCH_SIZE` limits the number
of rows processed by one invocation; `LLM_REQUEST_BATCH_SIZE` limits the
number of rows sent in one Gemini request. The recommended values above make
one request per invocation for ten articles. Eligible rows include
`claim_text_en` and `pubmed_query_en`, so the evidence Function can query
English PubMed abstracts without another Gemini request. The Function writes
successful rows when the internal time budget is reached. If Gemini is
unavailable, the quota is exhausted, or a response does not contain one valid
item per input row, that request's rows are not written and remain pending for
a later retry.
HTTP 4xx, quota, rate-limit, and malformed JSON failures are not retried
inside the same invocation, so a failed request does not consume a duplicate
API call.

## Output

Successful invocations write a CSV such as:

```text
silver/claims/claims_run_20261005T000000Z_ab12cd34.csv
```

The output keeps the Bronze and body columns and adds `claim_text`,
`claim_text_en`, `pubmed_query_en`, `query_status`, `query_prompt_version`,
`is_medical`, `is_claim_eligible`, `claim_type`, `llm_reason`,
`needs_human_review`, `llm_status`, `llm_error`, `llm_raw_json`, `model_id`,
`llm_key_slot`, `prompt_version`, timestamps, and source object/run identifiers.

## Enriching existing claim CSVs

CSV objects written before the English fields were added can be migrated
without downloading the news or extracting bodies again:

```bash
oci fn function invoke \
  --function-id <extract-claims-function-ocid> \
  --file - \
  --body '{"mode":"enrich_queries"}' \
  --region us-ashburn-1 \
  --read-timeout 360
```

This mode processes up to `LLM_BATCH_SIZE` existing eligible claims per call
and writes `claims_query_enriched_<run_id>.csv` in the same prefix. It is
idempotent: rows whose `query_status` is already `OK` are not enriched again.

## Manual invocation

```bash
oci fn function invoke \
  --function-id <extract-claims-function-ocid> \
  --file - \
  --body '' \
  --region us-ashburn-1 \
  --read-timeout 360
```
