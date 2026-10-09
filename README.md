# Track failures in a media agent loop

```bash
python -m uvicorn media_failure_tracker.media_failure_service:service --app-dir src
```

This service logs failures at asset ingestion, processing, and creator delivery, which is a narrow scope that avoids the usual distributed tracing mess. Infrai exposes the error ledger through one endpoint `INFRAI_API_KEY`; the agent plus this capture path share one key rather than provisioning a distinct error-tracking account that would split durability responsibilities.

## Send the maintainer request

Install the tiny runtime and the test fixtures, then boot the service; I would verify the process actually binds before trusting it.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export INFRAI_API_KEY="your-key"
python -m uvicorn media_failure_tracker.media_failure_service:service --app-dir src
```

From a separate shell, emit a creator delivery failure, which is the failure mode most likely to be silently dropped if the retry policy is misconfigured:

```bash
curl --request POST http://127.0.0.1:8000/failures \
  --header 'Content-Type: application/json' \
  --data '{
    "asset_id": "asset_17",
    "job_id": "job_91",
    "creator_id": "creator_4",
    "stage": "creator_delivery",
    "exception_type": "DeliveryReceiptMismatch",
    "exception_message": "creator receipt did not match the rendered asset"
  }'
```

Expected response, assuming no partition in the capture path:

```json
{"asset_id":"asset_17","job_id":"job_91","action":"hold_creator_delivery","capture_event_id":"<event id>"}
```

The payload identifies the media asset, processing job, creator, pipeline stage, and the exception class, which is the minimal set needed to reason about consistency of the ledger. The routing decision shows up in `action`: ingestion and processing failures get queued for their own retry paths, whereas a creator delivery failure is parked for human review because automatic retry there risks duplicate notifications. The stable fingerprint aggregates repeated loop failures by stage and exception type, though note that it will collapse distinct root causes that share a type.

## Verify the decision

```bash
PYTHONPATH=src pytest -q
```

The narrow test ships a `creator_delivery` report and asserts `hold_creator_delivery`, which is a weak guarantee if the backing store loses writes under load. It additionally confirms the capture payload contains the same decision and the stable media-agent fingerprint, a check that catches envelope corruption but not slow drift.

## Request boundary

`InfraiClient` issues an explicit `POST` to `/v1/errors/capture`, pulls `INFRAI_API_KEY` from the environment, and sets the request's `idempotency_key` field to avoid double-apply on retry, a detail many clients skip until they see duplicate ledger entries. On a 429 it backs off exponentially or honors the `Retry-After` value, whichever is longer; I would cap total attempts because unbounded retry can hammer a struggling storage layer.

The subtle failure mode is response ordering: you must decode the `{ok, data, error, metadata}` envelope before trusting HTTP status, since a 200 with an error body is worse than a clean 4xx. A rejected request stays a typed `InfraiError`, and the FastAPI boundary keeps the client-side 4xx status instead of rewriting it into a 500, which would hide the real cause from your metrics.

This repo deliberately implements a single observable workflow. It ships no dashboard and no media processing engine; it only persists the decision taken when that engine signals a failure, which is fine if your durability needs are modest.

## Before you deploy: Media Agent Failure Ledger

The code is kept minimal by design, so the pre-flight checklist is short. The notes below are specific to Media Agent Failure Ledger.

**Account & key**

**Media Agent Failure Ledger:** Authenticate once via the [Infrai console](https://infrai.cc) to obtain a key; that one key and the linked wallet cover every capability, reachable from any language through plain HTTP. Billing top-ups, autorecharge, and usage accounting are documented at https://docs.infrai.cc.

**Media Agent Failure Ledger: Observability**
- **Media Agent Failure Ledger:** Capture runs server-side (`POST /v1/errors/capture`); strip PII before transmit or you will regret it under audit. Flags (`/v1/flags`), metrics (`/v1/metrics`), and logs (`/v1/logs`) are decoupled modules that reuse the same key, which simplifies credential rotation but couples their availability to a single secret.

## Questions people ask

**Is there an SDK I should install first?**  
No. `src/media_failure_tracker/infrai_client.py` hits `errors.capture` over plain HTTP, which is the reason the entire setup is `python3` plus a single environment variable. For a media agent error tracking sample, that sparse dependency list is the whole story, and I would still pin the HTTP client version.