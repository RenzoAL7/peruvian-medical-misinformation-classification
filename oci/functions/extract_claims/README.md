# `extract-claims`

Third OCI Function in the thesis pipeline. It reads the article bodies already
written under `silver/body/`, skips rows without a body and rows whose body
extraction status is not `OK`, and extracts a candidate medical claim with
OCI Generative AI using `google.gemini-2.5-flash`.

The model is used only to structure the article into a candidate claim. It does
not decide whether the claim is true or false. Human review and evidence are
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
LLM_MAX_SECONDS=240
LLM_TIME_BUFFER=10
LLM_MAX_BODY_CHARS=12000
LLM_MAX_TOKENS=600
LLM_REQUEST_TIMEOUT=30
LLM_TEMPERATURE=0.1
LLM_TOP_P=0.9
LLM_MAX_RETRIES=1
```

The batch is filled across all CSVs in `silver/body/`, in deterministic object
name order. Record IDs already present in `silver/claims/` are skipped, so a
second invocation continues with new rows. The Function writes a partial
batch when the internal time budget is reached. If Generative AI is unavailable
or the tenancy quota is zero, failed rows are not written as claims and remain
pending for a later retry.

## Output

Successful invocations write a CSV such as:

```text
silver/claims/claims_batch_run_20261005T000000Z_ab12cd34.csv
```

The output keeps the Bronze and body columns and adds `claim_text`,
`is_medical`, `is_claim_eligible`, `claim_type`, `llm_reason`,
`needs_human_review`, `llm_status`, `llm_error`, `llm_raw_json`, `model_id`,
`prompt_version`, timestamps, and source object/run identifiers.

## Manual invocation

```bash
oci fn function invoke \
  --function-id <extract-claims-function-ocid> \
  --file - \
  --body '' \
  --region us-ashburn-1 \
  --read-timeout 360
```
