# integration-hub

A small hub that moves project records from one REST system to another (a project controls tool to an ERP) and does it safely: OAuth 2.0 tokens, retries, validation, master data mapping, no duplicates, a dead letter file, a trace from source id to target id and a reconciliation of totals. Both systems are fakes that run on local ports and can fail on purpose.

## What it handles

1. **Authentication** (`hub/auth.py`). OAuth 2.0 client credentials. The token is cached and fetched again shortly before it expires.
2. **Calls that fail** (`hub/http.py`). Timeouts, retry with exponential backoff on 429 and 5xx, `Retry-After` respected, and one token refresh on a 401.
3. **Mapping and validation** (`hub/mapping.py`). Task to cost line, with a work breakdown code to cost centre table, and clear reasons for bad input: missing field, unknown code, bad amount, unsupported currency, bad date.
4. **Sync** (`hub/sync.py`). A state file keeps the target id and a hash of what was sent. Unchanged records are skipped without a call, changed ones are updated with PUT, new ones are created with an idempotency key. Bad records go to a dead letter file with the reason.
5. **Reconciliation.** After each run the total sent is compared with the total the target reports.
6. **Webhooks** (`hub/webhook.py`). Signature check on the raw body with a time window against replays.

## Measured on the demo run

Synthetic data: 120 tasks, 6 of them with a defect. The target returns 429 once and 503 twice at the start.

|Measure|First run|Second run|
|-|-|-|
|created|114|0|
|unchanged (no call made)|0|114|
|dead letter (reason recorded)|6|6 (same records still fail)|
|source total = target total|yes (2,097,630 ore)|yes|
|retries absorbed|1 x 429, 2 x 503|none|

## Tests

11 tests in GitHub Actions: token cached then refreshed, a 503 retried until success, `Retry-After` honoured, a 401 causes one token refresh, bad records land in the dead letter file with a reason, a rerun creates no duplicates and makes no calls, a changed task is updated and not duplicated, totals reconcile, all pages are fetched, bad input is rejected, webhook signatures (valid, altered body, too old, wrong secret).

## A bug the tests found in my first version

My first generator applied every defect to every bad task, so all six dead letter reasons read "missing wbs" and the test for reasons failed. The generator now applies one defect per task.

## Run it

```
pip install -r requirements.txt
python -m pytest -q
python -m hub demo
```

## Limits

- The two systems are fakes I wrote. I have not connected to Oracle Primavera, SAP, Autodesk or Jira. The code uses only the Python standard library.
- No queue, no scheduler and no secrets store. The token and webhook secrets in the demo are placeholders.
- The state file is local. A real hub would keep it in a database.
- Power Platform, C# and VBA are not used here.
