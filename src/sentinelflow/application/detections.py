"""Authenticated inbound detection ingestion."""

import hashlib
import hmac
import time
from collections.abc import MutableSet
from uuid import UUID

from sentinelflow.application.incidents import IncidentService
from sentinelflow.domain import Incident, IncidentSeverity


class DetectionAuthenticationError(ValueError):
    """Webhook signature, timestamp, or replay validation failed."""


class ReplayGuard:
    def __init__(self) -> None:
        self._seen: MutableSet[str] = set()

    async def claim(self, event_id: str, ttl_seconds: int = 600) -> bool:
        del ttl_seconds
        if event_id in self._seen:
            return False
        self._seen.add(event_id)
        return True


class DetectionService:
    def __init__(
        self, incidents: IncidentService, secret: str, replay_guard: ReplayGuard | None = None
    ) -> None:
        if len(secret) < 32:
            raise ValueError("detection webhook secret must be at least 32 characters")
        self._incidents = incidents
        self._secret = secret.encode()
        self._replay = replay_guard or ReplayGuard()

    async def ingest(
        self,
        *,
        workspace_id: UUID,
        event_id: str,
        title: str,
        description: str,
        severity: IncidentSeverity,
        raw_body: bytes,
        timestamp: str,
        signature: str,
    ) -> Incident:
        try:
            timestamp_value = int(timestamp)
        except ValueError as exc:
            raise DetectionAuthenticationError("invalid webhook timestamp") from exc
        if abs(time.time() - timestamp_value) > 300:
            raise DetectionAuthenticationError("stale webhook timestamp")
        expected = hmac.new(
            self._secret, f"{timestamp}.".encode() + raw_body, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(signature.removeprefix("v1="), expected):
            raise DetectionAuthenticationError("invalid webhook signature")
        if not await self._replay.claim(event_id):
            raise DetectionAuthenticationError("replayed webhook event")
        return await self._incidents.create(
            workspace_id=workspace_id,
            title=title,
            description=description,
            severity=severity,
            actor_id="ai-soc:webhook",
            idempotency_key=f"aisoc:{event_id}",
        )
