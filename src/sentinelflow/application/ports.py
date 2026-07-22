"""Persistence ports used by the incident application service."""

from collections.abc import Sequence
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from sentinelflow.domain import Incident, IncidentEvent, IncidentStatus


class IncidentRepository(Protocol):
    """Workspace-scoped persistence operations for incidents and events."""

    async def add(self, incident: Incident, event: IncidentEvent) -> None: ...

    async def get(
        self, workspace_id: UUID, incident_id: UUID, *, for_update: bool = False
    ) -> Incident | None: ...

    async def list(
        self,
        workspace_id: UUID,
        *,
        status: IncidentStatus | None,
        limit: int,
        offset: int,
    ) -> Sequence[Incident]: ...

    async def save(self, incident: Incident, *, previous_version: int) -> None: ...

    async def add_event(self, event: IncidentEvent) -> None: ...

    async def get_event_by_idempotency(
        self, workspace_id: UUID, idempotency_key: str
    ) -> IncidentEvent | None: ...

    async def list_events(
        self,
        workspace_id: UUID,
        incident_id: UUID,
        *,
        after_sequence: int,
        limit: int,
    ) -> Sequence[IncidentEvent]: ...


class IncidentUnitOfWork(Protocol):
    """Atomic transaction boundary for an incident command."""

    incidents: IncidentRepository

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...
