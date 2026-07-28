"""Use cases for workspace-isolated incident lifecycle management."""

from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sentinelflow.application.ports import IncidentUnitOfWork
from sentinelflow.domain import (
    IdempotencyConflict,
    Incident,
    IncidentEvent,
    IncidentEventType,
    IncidentNotFound,
    IncidentSeverity,
    IncidentStatus,
    VersionConflict,
)
from sentinelflow.domain.incident import EventData

type UnitOfWorkFactory = Callable[[], IncidentUnitOfWork]
type Clock = Callable[[], datetime]
type IdFactory = Callable[[], UUID]


def utc_now() -> datetime:
    """Return an aware UTC timestamp."""
    return datetime.now(UTC)


class IncidentService:
    """Coordinate incident aggregates and their immutable timeline."""

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        *,
        clock: Clock = utc_now,
        id_factory: IdFactory = uuid4,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._clock = clock
        self._id_factory = id_factory

    async def create(
        self,
        *,
        workspace_id: UUID,
        title: str,
        description: str,
        severity: IncidentSeverity,
        actor_id: str,
        idempotency_key: str,
    ) -> Incident:
        """Create an incident and its first timeline event atomically."""
        event_data: EventData = {
            "title": title,
            "description": description,
            "severity": severity.value,
            "status": IncidentStatus.NEW.value,
        }
        async with self._unit_of_work_factory() as unit_of_work:
            existing = await unit_of_work.incidents.get_event_by_idempotency(
                workspace_id, idempotency_key
            )
            if existing is not None:
                self._assert_replay(
                    existing,
                    event_type=IncidentEventType.CREATED,
                    actor_id=actor_id,
                    data=event_data,
                )
                incident = await unit_of_work.incidents.get(workspace_id, existing.incident_id)
                if incident is None:
                    raise IncidentNotFound
                return incident

            now = self._clock()
            incident = Incident(
                id=self._id_factory(),
                workspace_id=workspace_id,
                title=title,
                description=description,
                severity=severity,
                status=IncidentStatus.NEW,
                version=1,
                created_at=now,
                updated_at=now,
            )
            event = IncidentEvent(
                id=self._id_factory(),
                workspace_id=workspace_id,
                incident_id=incident.id,
                sequence=1,
                event_type=IncidentEventType.CREATED,
                actor_id=actor_id,
                idempotency_key=idempotency_key,
                data=event_data,
                occurred_at=now,
            )
            await unit_of_work.incidents.add(incident, event)
            await unit_of_work.commit()
            return incident

    async def get(self, *, workspace_id: UUID, incident_id: UUID) -> Incident:
        """Get an incident only from the requested workspace."""
        async with self._unit_of_work_factory() as unit_of_work:
            incident = await unit_of_work.incidents.get(workspace_id, incident_id)
            if incident is None:
                raise IncidentNotFound
            return incident

    async def list(
        self,
        *,
        workspace_id: UUID,
        status: IncidentStatus | None,
        limit: int,
        offset: int,
    ) -> Sequence[Incident]:
        """List incidents scoped to one workspace."""
        async with self._unit_of_work_factory() as unit_of_work:
            return await unit_of_work.incidents.list(
                workspace_id, status=status, limit=limit, offset=offset
            )

    async def transition(
        self,
        *,
        workspace_id: UUID,
        incident_id: UUID,
        target: IncidentStatus,
        reason: str,
        expected_version: int,
        actor_id: str,
        idempotency_key: str,
    ) -> Incident:
        """Apply one explicit lifecycle transition with optimistic concurrency."""
        async with self._unit_of_work_factory() as unit_of_work:
            existing = await unit_of_work.incidents.get_event_by_idempotency(
                workspace_id, idempotency_key
            )
            if existing is not None:
                self._assert_transition_replay(
                    existing,
                    incident_id=incident_id,
                    target=target,
                    reason=reason,
                    expected_version=expected_version,
                    actor_id=actor_id,
                )
                replayed = await unit_of_work.incidents.get(workspace_id, incident_id)
                if replayed is None:
                    raise IncidentNotFound
                return replayed

            incident = await unit_of_work.incidents.get(workspace_id, incident_id, for_update=True)
            if incident is None:
                raise IncidentNotFound
            if incident.version != expected_version:
                raise VersionConflict(expected_version, incident.version)

            occurred_at = self._clock()
            previous_status = incident.transition(target, occurred_at)
            event = IncidentEvent(
                id=self._id_factory(),
                workspace_id=workspace_id,
                incident_id=incident.id,
                sequence=incident.version,
                event_type=IncidentEventType.STATUS_CHANGED,
                actor_id=actor_id,
                idempotency_key=idempotency_key,
                data={
                    "from": previous_status.value,
                    "to": target.value,
                    "reason": reason,
                },
                occurred_at=occurred_at,
            )
            await unit_of_work.incidents.save(incident, previous_version=expected_version)
            await unit_of_work.incidents.add_event(event)
            await unit_of_work.commit()
            return incident

    async def add_note(
        self,
        *,
        workspace_id: UUID,
        incident_id: UUID,
        body: str,
        expected_version: int,
        actor_id: str,
        idempotency_key: str,
    ) -> IncidentEvent:
        """Append an operator note without exposing an update/delete path."""
        event_data: EventData = {"body": body}
        async with self._unit_of_work_factory() as unit_of_work:
            existing = await unit_of_work.incidents.get_event_by_idempotency(
                workspace_id, idempotency_key
            )
            if existing is not None:
                self._assert_replay(
                    existing,
                    event_type=IncidentEventType.NOTE_ADDED,
                    actor_id=actor_id,
                    data=event_data,
                    incident_id=incident_id,
                    expected_version=expected_version,
                )
                return existing

            incident = await unit_of_work.incidents.get(workspace_id, incident_id, for_update=True)
            if incident is None:
                raise IncidentNotFound
            if incident.version != expected_version:
                raise VersionConflict(expected_version, incident.version)

            occurred_at = self._clock()
            incident.record_timeline_entry(occurred_at)
            event = IncidentEvent(
                id=self._id_factory(),
                workspace_id=workspace_id,
                incident_id=incident.id,
                sequence=incident.version,
                event_type=IncidentEventType.NOTE_ADDED,
                actor_id=actor_id,
                idempotency_key=idempotency_key,
                data=event_data,
                occurred_at=occurred_at,
            )
            await unit_of_work.incidents.save(incident, previous_version=expected_version)
            await unit_of_work.incidents.add_event(event)
            await unit_of_work.commit()
            return event

    async def timeline(
        self,
        *,
        workspace_id: UUID,
        incident_id: UUID,
        after_sequence: int,
        limit: int,
    ) -> Sequence[IncidentEvent]:
        """Return an ordered page of immutable incident events."""
        async with self._unit_of_work_factory() as unit_of_work:
            incident = await unit_of_work.incidents.get(workspace_id, incident_id)
            if incident is None:
                raise IncidentNotFound
            return await unit_of_work.incidents.list_events(
                workspace_id,
                incident_id,
                after_sequence=after_sequence,
                limit=limit,
            )

    @staticmethod
    def _assert_replay(
        event: IncidentEvent,
        *,
        event_type: IncidentEventType,
        actor_id: str,
        data: EventData,
        incident_id: UUID | None = None,
        expected_version: int | None = None,
    ) -> None:
        if (
            event.event_type is not event_type
            or event.actor_id != actor_id
            or event.data != data
            or (incident_id is not None and event.incident_id != incident_id)
            or (expected_version is not None and event.sequence != expected_version + 1)
        ):
            raise IdempotencyConflict

    @staticmethod
    def _assert_transition_replay(
        event: IncidentEvent,
        *,
        incident_id: UUID,
        target: IncidentStatus,
        reason: str,
        expected_version: int,
        actor_id: str,
    ) -> None:
        if (
            event.event_type is not IncidentEventType.STATUS_CHANGED
            or event.incident_id != incident_id
            or event.actor_id != actor_id
            or event.data.get("to") != target.value
            or event.data.get("reason") != reason
            or event.sequence != expected_version + 1
        ):
            raise IdempotencyConflict
