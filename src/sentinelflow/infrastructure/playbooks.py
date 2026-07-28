"""SQLAlchemy persistence adapter for versioned response playbooks."""

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

from sentinelflow.application.ports import PlaybookRepository
from sentinelflow.domain import (
    ConcurrentPlaybookWrite,
    InvalidPlaybookDefinition,
    Playbook,
    PlaybookEvent,
    PlaybookEventType,
    PlaybookStatus,
    PlaybookVersion,
)
from sentinelflow.domain.playbook import JsonObject, step_from_dict, step_to_dict
from sentinelflow.infrastructure.models import Base

PLAYBOOK_STATUS_TYPE = Enum(
    PlaybookStatus,
    name="playbook_status",
    native_enum=False,
    create_constraint=True,
    values_callable=lambda values: [value.value for value in values],
)
PLAYBOOK_EVENT_TYPE = Enum(
    PlaybookEventType,
    name="playbook_event_type",
    native_enum=False,
    create_constraint=True,
    values_callable=lambda values: [value.value for value in values],
)
JSON_DOCUMENT = JSON().with_variant(JSONB(), "postgresql")


class PlaybookRecord(Base):
    """Mutable playbook identity and active-revision pointer."""

    __tablename__ = "playbooks"
    __table_args__ = (
        CheckConstraint("length(name) > 0", name="name_not_empty"),
        CheckConstraint("latest_version >= 1", name="latest_version_positive"),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint(
            "active_version IS NULL OR active_version <= latest_version",
            name="active_version_valid",
        ),
        UniqueConstraint("id", "workspace_id", name="uq_playbooks_id_workspace"),
        Index("ix_playbooks_workspace_status_updated", "workspace_id", "status", "updated_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[PlaybookStatus] = mapped_column(PLAYBOOK_STATUS_TYPE, nullable=False)
    latest_version: Mapped[int] = mapped_column(Integer, nullable=False)
    active_version: Mapped[int | None] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PlaybookVersionRecord(Base):
    """Immutable content-addressed playbook definition."""

    __tablename__ = "playbook_versions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["playbook_id", "workspace_id"],
            ["playbooks.id", "playbooks.workspace_id"],
            name="fk_playbook_versions_playbook_workspace",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("playbook_id", "number", name="uq_playbook_versions_playbook_number"),
        UniqueConstraint("id", "workspace_id", name="uq_playbook_versions_id_workspace"),
        Index(
            "ix_playbook_versions_workspace_playbook",
            "workspace_id",
            "playbook_id",
            "number",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    playbook_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    steps: Mapped[list[JsonObject]] = mapped_column(JSON_DOCUMENT, nullable=False)
    definition_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PlaybookEventRecord(Base):
    """Append-only playbook audit and idempotency event."""

    __tablename__ = "playbook_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["playbook_id", "workspace_id"],
            ["playbooks.id", "playbooks.workspace_id"],
            name="fk_playbook_events_playbook_workspace",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("playbook_id", "sequence", name="uq_playbook_events_playbook_sequence"),
        UniqueConstraint(
            "workspace_id",
            "idempotency_key",
            name="uq_playbook_events_workspace_idempotency",
        ),
        Index(
            "ix_playbook_events_workspace_playbook",
            "workspace_id",
            "playbook_id",
            "sequence",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    playbook_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[PlaybookEventType] = mapped_column(PLAYBOOK_EVENT_TYPE, nullable=False)
    actor_id: Mapped[str] = mapped_column(String(200), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    data: Mapped[JsonObject] = mapped_column(JSON_DOCUMENT, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ImmutablePlaybookRecordError(RuntimeError):
    """Raised when immutable revision or event rows are changed."""


@event.listens_for(PlaybookVersionRecord, "before_update")
@event.listens_for(PlaybookVersionRecord, "before_delete")
@event.listens_for(PlaybookEventRecord, "before_update")
@event.listens_for(PlaybookEventRecord, "before_delete")
def prevent_immutable_playbook_record_mutation(
    _mapper: Mapper[Any],
    _connection: Connection,
    _target: PlaybookVersionRecord | PlaybookEventRecord,
) -> None:
    """Reject ORM mutation of immutable playbook records."""
    raise ImmutablePlaybookRecordError("Playbook versions and events are append-only")


class SQLAlchemyPlaybookRepository:
    """SQLAlchemy implementation of the workspace-scoped playbook port."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        playbook: Playbook,
        version: PlaybookVersion,
        audit_event: PlaybookEvent,
    ) -> None:
        self._session.add(self._playbook_record(playbook))
        await self._session.flush()
        self._session.add(self._version_record(version))
        self._session.add(self._event_record(audit_event))

    async def get(
        self, workspace_id: UUID, playbook_id: UUID, *, for_update: bool = False
    ) -> Playbook | None:
        statement = select(PlaybookRecord).where(
            PlaybookRecord.workspace_id == workspace_id,
            PlaybookRecord.id == playbook_id,
        )
        if for_update:
            statement = statement.with_for_update()
        record = (await self._session.execute(statement)).scalar_one_or_none()
        return self._playbook_domain(record) if record is not None else None

    async def list(
        self,
        workspace_id: UUID,
        *,
        status: PlaybookStatus | None,
        limit: int,
        offset: int,
    ) -> Sequence[Playbook]:
        statement = select(PlaybookRecord).where(PlaybookRecord.workspace_id == workspace_id)
        if status is not None:
            statement = statement.where(PlaybookRecord.status == status)
        statement = (
            statement.order_by(PlaybookRecord.updated_at.desc(), PlaybookRecord.id)
            .limit(limit)
            .offset(offset)
        )
        records = (await self._session.execute(statement)).scalars().all()
        return [self._playbook_domain(record) for record in records]

    async def save(self, playbook: Playbook, *, previous_version: int) -> None:
        result = cast(
            CursorResult[Any],
            await self._session.execute(
                update(PlaybookRecord)
                .where(
                    PlaybookRecord.workspace_id == playbook.workspace_id,
                    PlaybookRecord.id == playbook.id,
                    PlaybookRecord.version == previous_version,
                )
                .values(
                    status=playbook.status,
                    latest_version=playbook.latest_version,
                    active_version=playbook.active_version,
                    version=playbook.version,
                    updated_at=playbook.updated_at,
                    archived_at=playbook.archived_at,
                )
            ),
        )
        if result.rowcount != 1:
            raise ConcurrentPlaybookWrite

    async def add_version(self, version: PlaybookVersion) -> None:
        self._session.add(self._version_record(version))

    async def get_version(
        self, workspace_id: UUID, playbook_id: UUID, number: int
    ) -> PlaybookVersion | None:
        statement = select(PlaybookVersionRecord).where(
            PlaybookVersionRecord.workspace_id == workspace_id,
            PlaybookVersionRecord.playbook_id == playbook_id,
            PlaybookVersionRecord.number == number,
        )
        record = (await self._session.execute(statement)).scalar_one_or_none()
        return self._version_domain(record) if record is not None else None

    async def list_versions(
        self, workspace_id: UUID, playbook_id: UUID
    ) -> Sequence[PlaybookVersion]:
        statement = (
            select(PlaybookVersionRecord)
            .where(
                PlaybookVersionRecord.workspace_id == workspace_id,
                PlaybookVersionRecord.playbook_id == playbook_id,
            )
            .order_by(PlaybookVersionRecord.number.desc())
        )
        records = (await self._session.execute(statement)).scalars().all()
        return [self._version_domain(record) for record in records]

    async def add_event(self, audit_event: PlaybookEvent) -> None:
        self._session.add(self._event_record(audit_event))

    async def get_event_by_idempotency(
        self, workspace_id: UUID, idempotency_key: str
    ) -> PlaybookEvent | None:
        statement = select(PlaybookEventRecord).where(
            PlaybookEventRecord.workspace_id == workspace_id,
            PlaybookEventRecord.idempotency_key == idempotency_key,
        )
        record = (await self._session.execute(statement)).scalar_one_or_none()
        return self._event_domain(record) if record is not None else None

    async def list_events(
        self, workspace_id: UUID, playbook_id: UUID, *, limit: int
    ) -> Sequence[PlaybookEvent]:
        statement = (
            select(PlaybookEventRecord)
            .where(
                PlaybookEventRecord.workspace_id == workspace_id,
                PlaybookEventRecord.playbook_id == playbook_id,
            )
            .order_by(PlaybookEventRecord.sequence)
            .limit(limit)
        )
        records = (await self._session.execute(statement)).scalars().all()
        return [self._event_domain(record) for record in records]

    @staticmethod
    def _playbook_record(playbook: Playbook) -> PlaybookRecord:
        return PlaybookRecord(
            id=playbook.id,
            workspace_id=playbook.workspace_id,
            name=playbook.name,
            description=playbook.description,
            status=playbook.status,
            latest_version=playbook.latest_version,
            active_version=playbook.active_version,
            version=playbook.version,
            created_at=playbook.created_at,
            updated_at=playbook.updated_at,
            archived_at=playbook.archived_at,
        )

    @staticmethod
    def _version_record(version: PlaybookVersion) -> PlaybookVersionRecord:
        return PlaybookVersionRecord(
            id=version.id,
            workspace_id=version.workspace_id,
            playbook_id=version.playbook_id,
            number=version.number,
            steps=[step_to_dict(step) for step in version.steps],
            definition_hash=version.definition_hash,
            created_by=version.created_by,
            created_at=version.created_at,
        )

    @staticmethod
    def _event_record(audit_event: PlaybookEvent) -> PlaybookEventRecord:
        return PlaybookEventRecord(
            id=audit_event.id,
            workspace_id=audit_event.workspace_id,
            playbook_id=audit_event.playbook_id,
            sequence=audit_event.sequence,
            event_type=audit_event.event_type,
            actor_id=audit_event.actor_id,
            idempotency_key=audit_event.idempotency_key,
            data=audit_event.data,
            occurred_at=audit_event.occurred_at,
        )

    @staticmethod
    def _playbook_domain(record: PlaybookRecord) -> Playbook:
        return Playbook(
            id=record.id,
            workspace_id=record.workspace_id,
            name=record.name,
            description=record.description,
            status=record.status,
            latest_version=record.latest_version,
            active_version=record.active_version,
            version=record.version,
            created_at=record.created_at,
            updated_at=record.updated_at,
            archived_at=record.archived_at,
        )

    @staticmethod
    def _version_domain(record: PlaybookVersionRecord) -> PlaybookVersion:
        version = PlaybookVersion.build(
            id=record.id,
            workspace_id=record.workspace_id,
            playbook_id=record.playbook_id,
            number=record.number,
            steps=tuple(step_from_dict(dict(step)) for step in record.steps),
            created_by=record.created_by,
            created_at=record.created_at,
        )
        if version.definition_hash != record.definition_hash:
            raise InvalidPlaybookDefinition("Stored playbook definition hash does not match")
        return version

    @staticmethod
    def _event_domain(record: PlaybookEventRecord) -> PlaybookEvent:
        return PlaybookEvent(
            id=record.id,
            workspace_id=record.workspace_id,
            playbook_id=record.playbook_id,
            sequence=record.sequence,
            event_type=record.event_type,
            actor_id=record.actor_id,
            idempotency_key=record.idempotency_key,
            data=dict(record.data),
            occurred_at=record.occurred_at,
        )


class SQLAlchemyPlaybookUnitOfWork:
    """Async SQLAlchemy transaction boundary for playbook commands."""

    playbooks: PlaybookRepository

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None

    async def __aenter__(self) -> "SQLAlchemyPlaybookUnitOfWork":
        self._session = self._session_factory()
        self.playbooks = SQLAlchemyPlaybookRepository(self._session)
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
            raise ConcurrentPlaybookWrite from error
