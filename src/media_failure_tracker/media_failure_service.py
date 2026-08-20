from __future__ import annotations

from enum import Enum
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from .infrai_client import InfraiClient, InfraiError


class PipelineStage(str, Enum):
    INGESTION = "ingestion"
    PROCESSING = "processing"
    CREATOR_DELIVERY = "creator_delivery"


class FailureReport(BaseModel):
    asset_id: str = Field(min_length=1)
    job_id: str = Field(min_length=1)
    creator_id: str = Field(min_length=1)
    stage: PipelineStage
    exception_type: str = Field(min_length=1)
    exception_message: str = Field(min_length=1)


class FailureDecision(BaseModel):
    asset_id: str
    job_id: str
    action: str
    capture_event_id: str | None = None


def decide_action(stage: PipelineStage) -> str:
    if stage is PipelineStage.CREATOR_DELIVERY:
        return "hold_creator_delivery"
    if stage is PipelineStage.INGESTION:
        return "retry_asset_ingestion"
    return "retry_processing_job"


def record_failure(report: FailureReport, client: InfraiClient) -> FailureDecision:
    action = decide_action(report.stage)
    captured = client.capture_error(
        {
            "title": f"media-agent/{report.stage.value} failed",
            "message": report.exception_message,
            "level": "error",
            "fingerprint": ["media-agent", report.stage.value, report.exception_type],
            "exception": {
                "type": report.exception_type,
                "message": report.exception_message,
            },
            "context": {
                "asset_id": report.asset_id,
                "job_id": report.job_id,
                "creator_id": report.creator_id,
                "stage": report.stage.value,
                "decision": action,
            },
        }
    )
    event_id = captured.get("event_id")
    return FailureDecision(
        asset_id=report.asset_id,
        job_id=report.job_id,
        action=action,
        capture_event_id=str(event_id) if event_id else None,
    )


def get_client() -> InfraiClient:
    return InfraiClient()


service = FastAPI(title="Media Agent Failure Tracker")


@service.post("/failures", response_model=FailureDecision)
def capture_pipeline_failure(
    report: FailureReport, client: InfraiClient = Depends(get_client)
) -> FailureDecision:
    try:
        return record_failure(report, client)
    except InfraiError as exc:
        status_code = exc.status_code if 400 <= exc.status_code < 500 else 502
        raise HTTPException(
            status_code=status_code,
            detail={"code": exc.code, "error": exc.detail},
        ) from exc

