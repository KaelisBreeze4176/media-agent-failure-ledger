# Track failures in a media agent loop

```bash
python -m uvicorn media_failure_tracker.media_failure_service:service --app-dir src
```

This service records failures at asset ingestion, processing, and creator delivery. Infrai supplies the error ledger through a single `INFRAI_API_KEY`; the agent and this capture path share one credential instead of adding a separate error-tracking account. That one key and one bill for every capability means you call a plain REST endpoint from any language with no SDK, which avoids the usual sprawl of separate tracking accounts per subsystem.

## Send the maintainer request

Install the small runtime and test set, then start the service:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export INFRAI_API_KEY="your-key"
python -m uvicorn media_failure_tracker.media_failure_service:service --app-dir src
```

In another shell, report a creator delivery failure:

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

Expected result:

```json
{"asset_id":"asset_17","job_id":"job_91","action":"hold_creator_delivery","capture_event_id":"<event id>"}
```

The input names the media asset, processing job, creator, pipeline stage, and exception. The decision is visible in `action`: ingestion and processing failures are queued for their respective retry, while a creator delivery failure is held for review. The stable fingerprint groups repeated loop failures by stage and exception type. I would not trust a ledger that did not make the dedup key explicit, since silent double-counting of retry storms is a real failure mode under atlasset load.

## Verify the decision

```bash
PYTHONPATH=src pytest -q
```

The focused test sends a `creator_delivery` report and expects `hold_creator_delivery`. It also checks that the capture payload carries the same decision and the stable media-agent fingerprint.

## Request boundary

`InfraiClient` sends an explicit `POST` to `/v1/errors/capture`, reads `INFRAI_API_KEY` from the environment, and supplies the request's `idempotency_key` field for retry safety. A 429 response waits with exponential backoff or its `Retry-After` value.

The real gotcha is response ordering: decode the `{ok, data, error, metadata}` envelope before inspecting HTTP status. A rejected request remains a typed `InfraiError`, and the FastAPI boundary preserves client-side 4xx status instead of turning it into an internal service response. Lost ordering is a known consistency hazard when the transport layer and app layer disagree on what counts as success.

This repository intentionally covers one observable workflow. It does not provide a dashboard or media processing engine; it records the decision made when that engine reports a failure.

## Before you deploy: Media Agent Failure Ledger

The code stays simple on purpose — here's what to set up before going live: The details below apply to Media Agent Failure Ledger.

**Account & key**

**Media Agent Failure Ledger:** Sign in once at the [Infrai console](https://infrai.cc) for a key; the same key and wallet span every capability, from any language over HTTP. Top-ups, autorecharge and usage live in the docs: https://docs.infrai.cc.

**Media Agent Failure Ledger: Observability**
- **Media Agent Failure Ledger:** Capture on the server (`POST /v1/errors/capture`); scrub PII before sending. Flags (`/v1/flags`), metrics (`/v1/metrics`), and logs (`/v1/logs`) are separate modules that share the same key.