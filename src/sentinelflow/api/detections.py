"""Signed AI-SOC detection intake route."""

import json
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from sentinelflow.api.dependencies import get_detection_service
from sentinelflow.api.schemas import IncidentResponse
from sentinelflow.application.detections import DetectionAuthenticationError
from sentinelflow.domain import IncidentSeverity

router = APIRouter(prefix="/detections", tags=["detections"])


class DetectionPayload(BaseModel):
    event_id: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=10000)
    severity: IncidentSeverity


@router.post("/ai-soc", response_model=IncidentResponse, status_code=status.HTTP_201_CREATED)
async def ingest_ai_soc(
    request: Request,
    workspace_id: Annotated[UUID, Header(alias="X-Workspace-ID")],
    timestamp: Annotated[str, Header(alias="X-AI-SOC-Timestamp")],
    signature: Annotated[str, Header(alias="X-AI-SOC-Signature")],
) -> IncidentResponse:
    raw = await request.body()
    try:
        payload = DetectionPayload.model_validate(json.loads(raw))
        incident = await get_detection_service(request).ingest(
            workspace_id=workspace_id,
            raw_body=raw,
            timestamp=timestamp,
            signature=signature,
            **payload.model_dump(),
        )
    except (ValueError, DetectionAuthenticationError) as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return IncidentResponse.from_domain(incident)
