"""SQLAlchemy persistence for auditable workflow runs."""

from collections.abc import Sequence
from datetime import datetime
from types import TracebackType
from typing import Any, cast
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
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

from sentinelflow.application.ports import WorkflowRepository
from sentinelflow.domain import (
    ConcurrentWorkflowWrite,
    PlaybookStepKind,
    PlaybookStepRisk,
    PlaybookVersion,
    RollbackStrategy,
    WorkflowEvent,
    WorkflowEventType,
    WorkflowRun,
    WorkflowStatus,
    WorkflowStepRun,
    WorkflowStepStatus,
)
from sentinelflow.domain.playbook import JsonObject
from sentinelflow.infrastructure.incidents import IncidentRecord
from sentinelflow.infrastructure.models import Base
from sentinelflow.infrastructure.playbooks import (
    PlaybookVersionRecord,
    SQLAlchemyPlaybookRepository,
)

WORKFLOW_STATUS_TYPE = Enum(
    WorkflowStatus,
    name="workflow_status",
    native_enum=False,
    create_constraint=True,
    values_callable=lambda values: [value.value for value in values],
)
WORKFLOW_STEP_STATUS_TYPE = Enum(
    WorkflowStepStatus,
    name="workflow_step_status",
    native_enum=False,
    create_constraint=True,
    values_callable=lambda values: [value.value for value in values],
)
WORKFLOW_EVENT_TYPE = Enum(
    WorkflowEventType,
    name="workflow_event_type",
    native_enum=False,
    create_constraint=True,
    values_callable=lambda values: [value.value for value in values],
)
STEP_KIND_TYPE = Enum(
    PlaybookStepKind,
    name="workflow_step_kind",
    native_enum=False,
    create_constraint=True,
    values_callable=lambda values: [value.value for value in values],
)
STEP_RISK_TYPE = Enum(
    PlaybookStepRisk,
    name="workflow_step_risk",
    native_enum=False,
    create_constraint=True,
    values_callable=lambda values: [value.value for value in values],
)
ROLLBACK_STRATEGY_TYPE = Enum(
    RollbackStrategy,
    name="workflow_rollback_strategy",
    native_enum=False,
    create_constraint=True,
    values_callable=lambda values: [value.value for value in values],
)
JSON_DOCUMENT = JSON().with_variant(JSONB(), "postgresql")


class WorkflowRunRecord(Base):
    """Mutable workflow aggregate root."""

    __tablename__ = "workflow_runs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["incident_id", "workspace_id"],
            ["incidents.id", "incidents.workspace_id"],
            name="fk_workflow_runs_incident_workspace",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["playbook_version_id", "workspace_id"],
            ["playbook_versions.id", "playbook_versions.workspace_id"],
            name="fk_workflow_runs_playbook_version_workspace",
            ondelete="RESTRICT",
        ),
        CheckConstraint("version >= 1", name="workflow_version_positive"),
        CheckConstraint(
            "playbook_version >= 1",
            name="workflow_playbook_version_positive",
        ),
        UniqueConstraint("id", "workspace_id", name="uq_workflow_runs_id_workspace"),
        Index(
            "ix_workflow_runs_workspace_status_updated",
            "workspace_id",
            "status",
            "updated_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    incident_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    playbook_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    playbook_version_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    playbook_version: Mapped[int] = mapped_column(Integer, nullable=False)
    definition_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[WorkflowStatus] = mapped_column(WORKFLOW_STATUS_TYPE, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class WorkflowStepRecord(Base):
    """Mutable step state owned by one workflow aggregate."""

    __tablename__ = "workflow_steps"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workflow_id", "workspace_id"],
            ["workflow_runs.id", "workflow_runs.workspace_id"],
            name="fk_workflow_steps_workflow_workspace",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "position >= 0",
            name="workflow_step_position_nonnegative",
        ),
        CheckConstraint(
            "timeout_seconds BETWEEN 1 AND 3600",
            name="workflow_step_timeout",
        ),
        CheckConstraint(
            "max_attempts BETWEEN 1 AND 10",
            name="workflow_step_attempt_budget",
        ),
        CheckConstraint(
            "attempt >= 0",
            name="workflow_step_attempt_nonnegative",
        ),
        UniqueConstraint("workflow_id", "position", name="uq_workflow_steps_position"),
        UniqueConstraint("workflow_id", "step_key", name="uq_workflow_steps_key"),
        Index(
            "ix_workflow_steps_workspace_workflow",
            "workspace_id",
            "workflow_id",
            "position",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    workflow_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    step_key: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[PlaybookStepKind] = mapped_column(STEP_KIND_TYPE, nullable=False)
    risk: Mapped[PlaybookStepRisk] = mapped_column(STEP_RISK_TYPE, nullable=False)
    adapter: Mapped[str | None] = mapped_column(String(100))
    operation: Mapped[str | None] = mapped_column(String(100))
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    rollback_strategy: Mapped[RollbackStrategy | None] = mapped_column(ROLLBACK_STRATEGY_TYPE)
    rollback_operation: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[WorkflowStepStatus] = mapped_column(WORKFLOW_STEP_STATUS_TYPE, nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    output: Mapped[JsonObject] = mapped_column(JSON_DOCUMENT, nullable=False)
    last_error_code: Mapped[str | None] = mapped_column(String(100))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WorkflowEventRecord(Base):
    """Append-only workflow audit and idempotency event."""

    __tablename__ = "workflow_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workflow_id", "workspace_id"],
            ["workflow_runs.id", "workflow_runs.workspace_id"],
            name="fk_workflow_events_workflow_workspace",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("workflow_id", "sequence", name="uq_workflow_events_workflow_sequence"),
        UniqueConstraint(
            "workspace_id",
            "idempotency_key",
            name="uq_workflow_events_workspace_idempotency",
        ),
        Index(
            "ix_workflow_events_workspace_workflow",
            "workspace_id",
            "workflow_id",
            "sequence",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    workflow_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[WorkflowEventType] = mapped_column(WORKFLOW_EVENT_TYPE, nullable=False)
    actor_id: Mapped[str] = mapped_column(String(200), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    data: Mapped[JsonObject] = mapped_column(JSON_DOCUMENT, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ImmutableWorkflowEventError(RuntimeError):
    """Raised when code attempts to change a workflow audit event."""


@event.listens_for(WorkflowEventRecord, "before_update")
@event.listens_for(WorkflowEventRecord, "before_delete")
def prevent_workflow_event_mutation(
    _mapper: Mapper[Any], _connection: Connection, _target: WorkflowEventRecord
) -> None:
    raise ImmutableWorkflowEventError("Workflow events are append-only")


class SQLAlchemyWorkflowRepository:
    """SQLAlchemy implementation of the workflow persistence port."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, workflow: WorkflowRun, audit_event: WorkflowEvent) -> None:
        self._session.add(self._run_record(workflow))
        await self._session.flush()
        self._session.add_all([self._step_record(step) for step in workflow.steps])
        self._session.add(self._event_record(audit_event))

    async def get(
        self, workspace_id: UUID, workflow_id: UUID, *, for_update: bool = False
    ) -> WorkflowRun | None:
        statement = select(WorkflowRunRecord).where(
            WorkflowRunRecord.workspace_id == workspace_id,
            WorkflowRunRecord.id == workflow_id,
        )
        if for_update:
            statement = statement.with_for_update()
        record = (await self._session.execute(statement)).scalar_one_or_none()
        if record is None:
            return None
        return await self._run_domain(record)

    async def list(
        self,
        workspace_id: UUID,
        *,
        status: WorkflowStatus | None,
        limit: int,
        offset: int,
    ) -> Sequence[WorkflowRun]:
        statement = select(WorkflowRunRecord).where(WorkflowRunRecord.workspace_id == workspace_id)
        if status is not None:
            statement = statement.where(WorkflowRunRecord.status == status)
        statement = (
            statement.order_by(WorkflowRunRecord.updated_at.desc(), WorkflowRunRecord.id)
            .limit(limit)
            .offset(offset)
        )
        records = (await self._session.execute(statement)).scalars().all()
        return [await self._run_domain(record) for record in records]

    async def save(self, workflow: WorkflowRun, *, previous_version: int) -> None:
        result = cast(
            CursorResult[Any],
            await self._session.execute(
                update(WorkflowRunRecord)
                .where(
                    WorkflowRunRecord.workspace_id == workflow.workspace_id,
                    WorkflowRunRecord.id == workflow.id,
                    WorkflowRunRecord.version == previous_version,
                )
                .values(
                    status=workflow.status,
                    version=workflow.version,
                    updated_at=workflow.updated_at,
                    started_at=workflow.started_at,
                    finished_at=workflow.finished_at,
                    cancel_requested=workflow.cancel_requested,
                )
            ),
        )
        if result.rowcount != 1:
            raise ConcurrentWorkflowWrite
        for step in workflow.steps:
            await self._session.execute(
                update(WorkflowStepRecord)
                .where(
                    WorkflowStepRecord.workspace_id == workflow.workspace_id,
                    WorkflowStepRecord.workflow_id == workflow.id,
                    WorkflowStepRecord.id == step.id,
                )
                .values(
                    status=step.status,
                    attempt=step.attempt,
                    output=step.output,
                    last_error_code=step.last_error_code,
                    started_at=step.started_at,
                    finished_at=step.finished_at,
                )
            )

    async def resolve_dependencies(
        self,
        workspace_id: UUID,
        incident_id: UUID,
        playbook_id: UUID,
        playbook_version: int,
    ) -> PlaybookVersion | None:
        incident = (
            await self._session.execute(
                select(IncidentRecord.id).where(
                    IncidentRecord.workspace_id == workspace_id,
                    IncidentRecord.id == incident_id,
                )
            )
        ).scalar_one_or_none()
        if incident is None:
            return None
        record = (
            await self._session.execute(
                select(PlaybookVersionRecord).where(
                    PlaybookVersionRecord.workspace_id == workspace_id,
                    PlaybookVersionRecord.playbook_id == playbook_id,
                    PlaybookVersionRecord.number == playbook_version,
                )
            )
        ).scalar_one_or_none()
        if record is None:
            return None
        return SQLAlchemyPlaybookRepository._version_domain(record)

    async def add_event(self, audit_event: WorkflowEvent) -> None:
        self._session.add(self._event_record(audit_event))

    async def get_event_by_idempotency(
        self, workspace_id: UUID, idempotency_key: str
    ) -> WorkflowEvent | None:
        record = (
            await self._session.execute(
                select(WorkflowEventRecord).where(
                    WorkflowEventRecord.workspace_id == workspace_id,
                    WorkflowEventRecord.idempotency_key == idempotency_key,
                )
            )
        ).scalar_one_or_none()
        return self._event_domain(record) if record is not None else None

    async def list_events(
        self, workspace_id: UUID, workflow_id: UUID, *, limit: int
    ) -> Sequence[WorkflowEvent]:
        records = (
            (
                await self._session.execute(
                    select(WorkflowEventRecord)
                    .where(
                        WorkflowEventRecord.workspace_id == workspace_id,
                        WorkflowEventRecord.workflow_id == workflow_id,
                    )
                    .order_by(WorkflowEventRecord.sequence)
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        return [self._event_domain(record) for record in records]

    async def _run_domain(self, record: WorkflowRunRecord) -> WorkflowRun:
        step_records = (
            (
                await self._session.execute(
                    select(WorkflowStepRecord)
                    .where(
                        WorkflowStepRecord.workspace_id == record.workspace_id,
                        WorkflowStepRecord.workflow_id == record.id,
                    )
                    .order_by(WorkflowStepRecord.position)
                )
            )
            .scalars()
            .all()
        )
        return WorkflowRun(
            id=record.id,
            workspace_id=record.workspace_id,
            incident_id=record.incident_id,
            playbook_id=record.playbook_id,
            playbook_version_id=record.playbook_version_id,
            playbook_version=record.playbook_version,
            definition_hash=record.definition_hash,
            status=record.status,
            version=record.version,
            created_by=record.created_by,
            created_at=record.created_at,
            updated_at=record.updated_at,
            started_at=record.started_at,
            finished_at=record.finished_at,
            cancel_requested=record.cancel_requested,
            steps=[self._step_domain(step) for step in step_records],
        )

    @staticmethod
    def _run_record(workflow: WorkflowRun) -> WorkflowRunRecord:
        return WorkflowRunRecord(
            id=workflow.id,
            workspace_id=workflow.workspace_id,
            incident_id=workflow.incident_id,
            playbook_id=workflow.playbook_id,
            playbook_version_id=workflow.playbook_version_id,
            playbook_version=workflow.playbook_version,
            definition_hash=workflow.definition_hash,
            status=workflow.status,
            version=workflow.version,
            created_by=workflow.created_by,
            created_at=workflow.created_at,
            updated_at=workflow.updated_at,
            started_at=workflow.started_at,
            finished_at=workflow.finished_at,
            cancel_requested=workflow.cancel_requested,
        )

    @staticmethod
    def _step_record(step: WorkflowStepRun) -> WorkflowStepRecord:
        return WorkflowStepRecord(
            id=step.id,
            workspace_id=step.workspace_id,
            workflow_id=step.workflow_id,
            position=step.position,
            step_key=step.step_key,
            name=step.name,
            kind=step.kind,
            risk=step.risk,
            adapter=step.adapter,
            operation=step.operation,
            timeout_seconds=step.timeout_seconds,
            max_attempts=step.max_attempts,
            rollback_strategy=step.rollback_strategy,
            rollback_operation=step.rollback_operation,
            status=step.status,
            attempt=step.attempt,
            output=step.output,
            last_error_code=step.last_error_code,
            started_at=step.started_at,
            finished_at=step.finished_at,
        )

    @staticmethod
    def _event_record(audit_event: WorkflowEvent) -> WorkflowEventRecord:
        return WorkflowEventRecord(
            id=audit_event.id,
            workspace_id=audit_event.workspace_id,
            workflow_id=audit_event.workflow_id,
            sequence=audit_event.sequence,
            event_type=audit_event.event_type,
            actor_id=audit_event.actor_id,
            idempotency_key=audit_event.idempotency_key,
            data=audit_event.data,
            occurred_at=audit_event.occurred_at,
        )

    @staticmethod
    def _step_domain(record: WorkflowStepRecord) -> WorkflowStepRun:
        return WorkflowStepRun(
            id=record.id,
            workspace_id=record.workspace_id,
            workflow_id=record.workflow_id,
            position=record.position,
            step_key=record.step_key,
            name=record.name,
            kind=record.kind,
            risk=record.risk,
            adapter=record.adapter,
            operation=record.operation,
            timeout_seconds=record.timeout_seconds,
            max_attempts=record.max_attempts,
            rollback_strategy=record.rollback_strategy,
            rollback_operation=record.rollback_operation,
            status=record.status,
            attempt=record.attempt,
            output=dict(record.output),
            last_error_code=record.last_error_code,
            started_at=record.started_at,
            finished_at=record.finished_at,
        )

    @staticmethod
    def _event_domain(record: WorkflowEventRecord) -> WorkflowEvent:
        return WorkflowEvent(
            id=record.id,
            workspace_id=record.workspace_id,
            workflow_id=record.workflow_id,
            sequence=record.sequence,
            event_type=record.event_type,
            actor_id=record.actor_id,
            idempotency_key=record.idempotency_key,
            data=dict(record.data),
            occurred_at=record.occurred_at,
        )


class SQLAlchemyWorkflowUnitOfWork:
    """Async SQLAlchemy transaction boundary for workflow commands."""

    workflows: WorkflowRepository

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None

    async def __aenter__(self) -> "SQLAlchemyWorkflowUnitOfWork":
        self._session = self._session_factory()
        self.workflows = SQLAlchemyWorkflowRepository(self._session)
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
            raise ConcurrentWorkflowWrite from error
