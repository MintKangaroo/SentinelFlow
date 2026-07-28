"""Persistence ports used by the incident application service."""

from collections.abc import Sequence
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from sentinelflow.domain import (
    Incident,
    IncidentEvent,
    IncidentStatus,
    Playbook,
    PlaybookEvent,
    PlaybookStatus,
    PlaybookVersion,
    WorkflowEvent,
    WorkflowRun,
    WorkflowStatus,
)


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


class PlaybookRepository(Protocol):
    """Workspace-scoped persistence operations for immutable playbook revisions."""

    async def add(
        self,
        playbook: Playbook,
        version: PlaybookVersion,
        event: PlaybookEvent,
    ) -> None: ...

    async def get(
        self, workspace_id: UUID, playbook_id: UUID, *, for_update: bool = False
    ) -> Playbook | None: ...

    async def list(
        self,
        workspace_id: UUID,
        *,
        status: PlaybookStatus | None,
        limit: int,
        offset: int,
    ) -> Sequence[Playbook]: ...

    async def save(self, playbook: Playbook, *, previous_version: int) -> None: ...

    async def add_version(self, version: PlaybookVersion) -> None: ...

    async def get_version(
        self, workspace_id: UUID, playbook_id: UUID, number: int
    ) -> PlaybookVersion | None: ...

    async def list_versions(
        self, workspace_id: UUID, playbook_id: UUID
    ) -> Sequence[PlaybookVersion]: ...

    async def add_event(self, event: PlaybookEvent) -> None: ...

    async def get_event_by_idempotency(
        self, workspace_id: UUID, idempotency_key: str
    ) -> PlaybookEvent | None: ...

    async def list_events(
        self, workspace_id: UUID, playbook_id: UUID, *, limit: int
    ) -> Sequence[PlaybookEvent]: ...


class PlaybookUnitOfWork(Protocol):
    """Atomic transaction boundary for playbook commands."""

    playbooks: PlaybookRepository

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...


class WorkflowRepository(Protocol):
    """Workspace-scoped persistence for workflow aggregates and events."""

    async def add(self, workflow: WorkflowRun, event: WorkflowEvent) -> None: ...

    async def get(
        self, workspace_id: UUID, workflow_id: UUID, *, for_update: bool = False
    ) -> WorkflowRun | None: ...

    async def list(
        self,
        workspace_id: UUID,
        *,
        status: WorkflowStatus | None,
        limit: int,
        offset: int,
    ) -> Sequence[WorkflowRun]: ...

    async def save(self, workflow: WorkflowRun, *, previous_version: int) -> None: ...

    async def resolve_dependencies(
        self,
        workspace_id: UUID,
        incident_id: UUID,
        playbook_id: UUID,
        playbook_version: int,
    ) -> PlaybookVersion | None: ...

    async def add_event(self, event: WorkflowEvent) -> None: ...

    async def get_event_by_idempotency(
        self, workspace_id: UUID, idempotency_key: str
    ) -> WorkflowEvent | None: ...

    async def list_events(
        self, workspace_id: UUID, workflow_id: UUID, *, limit: int
    ) -> Sequence[WorkflowEvent]: ...


class WorkflowUnitOfWork(Protocol):
    """Atomic transaction boundary for workflow commands."""

    workflows: WorkflowRepository

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...
