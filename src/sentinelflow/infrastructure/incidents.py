"""SQLAlchemy persistence adapter for Incident and IncidentEvent."""

from collections.abc import Sequence
from datetime import datetime
from types import TracebackType
from typing import Any, cast
from uuid import UUID

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    event,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Connection, CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, Mapper, mapped_column

from sentinelflow.application.ports import IncidentRepository
from sentinelflow.domain import (
    ConcurrentIncidentWrite,
    Incident,
    IncidentEvent,
    IncidentEventType,
    IncidentSeverity,
    IncidentStatus,
)
from sentinelflow.domain.incident import EventData
from sentinelflow.infrastructure.models import Base

INCIDENT_STATUS_TYPE = Enum(
    IncidentStatus,
    name="incident_status",
    native_enum=False,
    create_constraint=True,
    values_callable=lambda values: [value.value for value in values],
)
INCIDENT_SEVERITY_TYPE = Enum(
    IncidentSeverity,
    name="incident_severity",
    native_enum=False,
    create_constraint=True,
    values_callable=lambda values: [value.value for value in values],
)
INCIDENT_EVENT_TYPE = Enum(
    IncidentEventType,
    name="incident_event_type",
    native_enum=False,
    create_constraint=True,
    values_callable=lambda values: [value.value for value in values],
)
EVENT_DATA_TYPE = JSON().with_variant(JSONB(), "postgresql")


class IncidentRecord(Base):
    """Relational representation of an incident aggregate."""

    __tablename__ = "incidents"
    __table_args__ = (
        CheckConstraint("length(title) > 0", name="title_not_empty"),
        UniqueConstraint("id", "workspace_id", name="uq_incidents_id_workspace"),
        Index("ix_incidents_workspace_status_updated", "workspace_id", "status", "updated_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    severity: Mapped[IncidentSeverity] = mapped_column(INCIDENT_SEVERITY_TYPE, nullable=False)
    status: Mapped[IncidentStatus] = mapped_column(INCIDENT_STATUS_TYPE, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IncidentEventRecord(Base):
    """Append-only relational representation of a timeline event."""

    __tablename__ = "incident_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["incident_id", "workspace_id"],
            ["incidents.id", "incidents.workspace_id"],
            name="fk_incident_events_incident_workspace",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("incident_id", "sequence", name="uq_incident_events_incident_sequence"),
        UniqueConstraint(
            "workspace_id",
            "idempotency_key",
            name="uq_incident_events_workspace_idempotency",
        ),
        Index("ix_incident_events_workspace_incident", "workspace_id", "incident_id", "sequence"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    incident_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[IncidentEventType] = mapped_column(INCIDENT_EVENT_TYPE, nullable=False)
    actor_id: Mapped[str] = mapped_column(String(200), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    data: Mapped[EventData] = mapped_column(EVENT_DATA_TYPE, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ImmutableIncidentEventError(RuntimeError):
    """Raised when code attempts to mutate an append-only timeline record."""


@event.listens_for(IncidentEventRecord, "before_update")
def prevent_incident_event_update(
    _mapper: Mapper[Any], _connection: Connection, _target: IncidentEventRecord
) -> None:
    """Reject ORM updates to timeline records."""
    raise ImmutableIncidentEventError("Incident events are append-only")


@event.listens_for(IncidentEventRecord, "before_delete")
def prevent_incident_event_delete(
    _mapper: Mapper[Any], _connection: Connection, _target: IncidentEventRecord
) -> None:
    """Reject ORM deletes from the timeline."""
    raise ImmutableIncidentEventError("Incident events are append-only")


class SQLAlchemyIncidentRepository:
    """Workspace-scoped SQLAlchemy implementation of the incident port."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, incident: Incident, timeline_event: IncidentEvent) -> None:
        self._session.add(self._incident_record(incident))
        await self._session.flush()
        self._session.add(self._event_record(timeline_event))

    async def get(
        self, workspace_id: UUID, incident_id: UUID, *, for_update: bool = False
    ) -> Incident | None:
        statement = select(IncidentRecord).where(
            IncidentRecord.workspace_id == workspace_id,
            IncidentRecord.id == incident_id,
        )
        if for_update:
            statement = statement.with_for_update()
        record = (await self._session.execute(statement)).scalar_one_or_none()
        return self._incident_domain(record) if record is not None else None

    async def list(
        self,
        workspace_id: UUID,
        *,
        status: IncidentStatus | None,
        limit: int,
        offset: int,
    ) -> Sequence[Incident]:
        statement = select(IncidentRecord).where(IncidentRecord.workspace_id == workspace_id)
        if status is not None:
            statement = statement.where(IncidentRecord.status == status)
        statement = (
            statement.order_by(IncidentRecord.updated_at.desc(), IncidentRecord.id)
            .limit(limit)
            .offset(offset)
        )
        records = (await self._session.execute(statement)).scalars().all()
        return [self._incident_domain(record) for record in records]

    async def save(self, incident: Incident, *, previous_version: int) -> None:
        result = cast(
            CursorResult[Any],
            await self._session.execute(
                update(IncidentRecord)
                .where(
                    IncidentRecord.workspace_id == incident.workspace_id,
                    IncidentRecord.id == incident.id,
                    IncidentRecord.version == previous_version,
                )
                .values(
                    status=incident.status,
                    version=incident.version,
                    updated_at=incident.updated_at,
                    resolved_at=incident.resolved_at,
                    closed_at=incident.closed_at,
                )
            ),
        )
        if result.rowcount != 1:
            raise ConcurrentIncidentWrite

    async def add_event(self, timeline_event: IncidentEvent) -> None:
        self._session.add(self._event_record(timeline_event))

    async def get_event_by_idempotency(
        self, workspace_id: UUID, idempotency_key: str
    ) -> IncidentEvent | None:
        statement = select(IncidentEventRecord).where(
            IncidentEventRecord.workspace_id == workspace_id,
            IncidentEventRecord.idempotency_key == idempotency_key,
        )
        record = (await self._session.execute(statement)).scalar_one_or_none()
        return self._event_domain(record) if record is not None else None

    async def list_events(
        self,
        workspace_id: UUID,
        incident_id: UUID,
        *,
        after_sequence: int,
        limit: int,
    ) -> Sequence[IncidentEvent]:
        statement = (
            select(IncidentEventRecord)
            .where(
                IncidentEventRecord.workspace_id == workspace_id,
                IncidentEventRecord.incident_id == incident_id,
                IncidentEventRecord.sequence > after_sequence,
            )
            .order_by(IncidentEventRecord.sequence)
            .limit(limit)
        )
        records = (await self._session.execute(statement)).scalars().all()
        return [self._event_domain(record) for record in records]

    @staticmethod
    def _incident_record(incident: Incident) -> IncidentRecord:
        return IncidentRecord(
            id=incident.id,
            workspace_id=incident.workspace_id,
            title=incident.title,
            description=incident.description,
            severity=incident.severity,
            status=incident.status,
            version=incident.version,
            created_at=incident.created_at,
            updated_at=incident.updated_at,
            resolved_at=incident.resolved_at,
            closed_at=incident.closed_at,
        )

    @staticmethod
    def _event_record(timeline_event: IncidentEvent) -> IncidentEventRecord:
        return IncidentEventRecord(
            id=timeline_event.id,
            workspace_id=timeline_event.workspace_id,
            incident_id=timeline_event.incident_id,
            sequence=timeline_event.sequence,
            event_type=timeline_event.event_type,
            actor_id=timeline_event.actor_id,
            idempotency_key=timeline_event.idempotency_key,
            data=timeline_event.data,
            occurred_at=timeline_event.occurred_at,
        )

    @staticmethod
    def _incident_domain(record: IncidentRecord) -> Incident:
        return Incident(
            id=record.id,
            workspace_id=record.workspace_id,
            title=record.title,
            description=record.description,
            severity=record.severity,
            status=record.status,
            version=record.version,
            created_at=record.created_at,
            updated_at=record.updated_at,
            resolved_at=record.resolved_at,
            closed_at=record.closed_at,
        )

    @staticmethod
    def _event_domain(record: IncidentEventRecord) -> IncidentEvent:
        return IncidentEvent(
            id=record.id,
            workspace_id=record.workspace_id,
            incident_id=record.incident_id,
            sequence=record.sequence,
            event_type=record.event_type,
            actor_id=record.actor_id,
            idempotency_key=record.idempotency_key,
            data=dict(record.data),
            occurred_at=record.occurred_at,
        )


class SQLAlchemyIncidentUnitOfWork:
    """Async SQLAlchemy transaction boundary for incident commands."""

    incidents: IncidentRepository

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None

    async def __aenter__(self) -> "SQLAlchemyIncidentUnitOfWork":
        self._session = self._session_factory()
        self.incidents = SQLAlchemyIncidentRepository(self._session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        _exc_value: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        if self._session is None:
            return
        if exc_type is not None:
            await self._session.rollback()
        await self._session.close()

    async def commit(self) -> None:
        if self._session is None:
            raise RuntimeError("Unit of work has not been entered")
        try:
            await self._session.commit()
        except IntegrityError as error:
            await self._session.rollback()
            raise ConcurrentIncidentWrite from error
