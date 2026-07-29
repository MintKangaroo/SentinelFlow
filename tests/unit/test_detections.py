import hashlib
import hmac
import time
from uuid import uuid4

import pytest

from sentinelflow.application.detections import DetectionAuthenticationError, DetectionService
from sentinelflow.domain import IncidentSeverity


@pytest.mark.asyncio
async def test_signed_detection_creates_incident_and_rejects_replay(incident_runtime) -> None:
    webhook_key = "detection-key-01234567890123456789012345"
    service = DetectionService(incident_runtime.service, webhook_key)
    workspace = uuid4()
    body = b'{"event_id":"evt-1"}'
    timestamp = str(int(time.time()))
    signature = hmac.new(
        webhook_key.encode(), f"{timestamp}.".encode() + body, hashlib.sha256
    ).hexdigest()
    incident = await service.ingest(
        workspace_id=workspace,
        event_id="evt-1",
        title="Signed alert",
        description="evidence",
        severity=IncidentSeverity.HIGH,
        raw_body=body,
        timestamp=timestamp,
        signature=f"v1={signature}",
    )
    assert incident.title == "Signed alert"
    with pytest.raises(DetectionAuthenticationError):
        await service.ingest(
            workspace_id=workspace,
            event_id="evt-1",
            title="Signed alert",
            description="evidence",
            severity=IncidentSeverity.HIGH,
            raw_body=body,
            timestamp=timestamp,
            signature=signature,
        )


@pytest.mark.asyncio
async def test_detection_rejects_stale_and_invalid_signatures(incident_runtime) -> None:
    service = DetectionService(incident_runtime.service, "detection-key-01234567890123456789012345")
    with pytest.raises(DetectionAuthenticationError):
        await service.ingest(
            workspace_id=uuid4(),
            event_id="stale",
            title="",
            description="",
            severity=IncidentSeverity.LOW,
            raw_body=b"{}",
            timestamp="1",
            signature="bad",
        )
