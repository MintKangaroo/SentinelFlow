"""SQLAlchemy persistence for risk-based approval requests."""

from collections.abc import Sequence
from datetime import UTC, datetime
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

from sentinelflow.application.ports import ApprovalRepository
from sentinelflow.domain import (
    ApprovalDecision,
    ApprovalDecisionValue,
    ApprovalEvent,
    ApprovalEventType,
    ApprovalRequest,
    ApprovalStatus,
    ConcurrentApprovalWrite,
    PlaybookStepRisk,
    WorkflowStatus,
    WorkflowStepStatus,
)
from sentinelflow.domain.playbook import JsonObject
from sentinelflow.infrastructure.models import Base
from sentinelflow.infrastructure.workflows import WorkflowRunRecord, WorkflowStepRecord

JSON_DOCUMENT = JSON().with_variant(JSONB(), "postgresql")
APPROVAL_STATUS_TYPE = Enum(
    ApprovalStatus,
    name="approval_status",
    native_enum=False,
    create_constraint=True,
    values_callable=lambda values: [value.value for value in values],
)
APPROVAL_DECISION_TYPE = Enum(
    ApprovalDecisionValue,
    name="approval_decision",
    native_enum=False,
    create_constraint=True,
    values_callable=lambda values: [value.value for value in values],
)
APPROVAL_EVENT_TYPE = Enum(
    ApprovalEventType,
    name="approval_event_type",
    native_enum=False,
    create_constraint=True,
    values_callable=lambda values: [value.value for value in values],
)
APPROVAL_RISK_TYPE = Enum(
    PlaybookStepRisk,
    name="approval_risk",
    native_enum=False,
    create_constraint=True,
    values_callable=lambda values: [value.value for value in values],
)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)


class ApprovalRequestRecord(Base):
    """Mutable approval aggregate root."""

    __tablename__ = "approval_requests"
    __table_args__ = (
        ForeignKeyConstraint(
            ["incident_id", "workspace_id"],
            ["incidents.id", "incidents.workspace_id"],
            name="fk_approval_requests_incident_workspace",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["workflow_id", "workspace_id"],
            ["workflow_runs.id", "workflow_runs.workspace_id"],
            name="fk_approval_requests_workflow_workspace",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "required_approvals BETWEEN 1 AND 5",
            name="approval_required_count",
        ),
        CheckConstraint("version >= 1", name="approval_version_positive"),
        CheckConstraint("round >= 1", name="approval_round_positive"),
        UniqueConstraint("id", "workspace_id", name="uq_approval_requests_id_workspace"),
        UniqueConstraint(
            "workflow_id",
            "step_key",
            name="uq_approval_requests_workflow_step",
        ),
        Index(
            "ix_approval_requests_workspace_status_updated",
            "workspace_id",
            "status",
            "updated_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    incident_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    workflow_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    step_key: Mapped[str] = mapped_column(String(64), nullable=False)
    action_summary: Mapped[str] = mapped_column(String(300), nullable=False)
    risk: Mapped[PlaybookStepRisk] = mapped_column(APPROVAL_RISK_TYPE, nullable=False)
    status: Mapped[ApprovalStatus] = mapped_column(APPROVAL_STATUS_TYPE, nullable=False)
    required_approvals: Mapped[int] = mapped_column(Integer, nullable=False)
    eligible_roles: Mapped[list[str]] = mapped_column(JSON_DOCUMENT, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    round: Mapped[int] = mapped_column(Integer, nullable=False)
    requested_by: Mapped[str] = mapped_column(String(200), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ApprovalDecisionRecord(Base):
    """Immutable actor decision retained for every approval round."""

    __tablename__ = "approval_decisions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["approval_id", "workspace_id"],
            ["approval_requests.id", "approval_requests.workspace_id"],
            name="fk_approval_decisions_request_workspace",
            ondelete="RESTRICT",
        ),
        CheckConstraint("round >= 1", name="approval_decision_round_positive"),
        UniqueConstraint(
            "approval_id",
            "round",
            "actor_id",
            name="uq_approval_decisions_round_actor",
        ),
        Index(
            "ix_approval_decisions_workspace_request",
            "workspace_id",
            "approval_id",
            "round",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    approval_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    round: Mapped[int] = mapped_column(Integer, nullable=False)
    actor_id: Mapped[str] = mapped_column(String(200), nullable=False)
    actor_role: Mapped[str] = mapped_column(String(100), nullable=False)
    decision: Mapped[ApprovalDecisionValue] = mapped_column(APPROVAL_DECISION_TYPE, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ApprovalEventRecord(Base):
    """Append-only approval audit and idempotency event."""

    __tablename__ = "approval_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["approval_id", "workspace_id"],
            ["approval_requests.id", "approval_requests.workspace_id"],
            name="fk_approval_events_request_workspace",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("approval_id", "sequence", name="uq_approval_events_sequence"),
        UniqueConstraint(
            "workspace_id",
            "idempotency_key",
            name="uq_approval_events_workspace_idempotency",
        ),
        Index(
            "ix_approval_events_workspace_request",
            "workspace_id",
            "approval_id",
            "sequence",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    approval_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[ApprovalEventType] = mapped_column(APPROVAL_EVENT_TYPE, nullable=False)
    actor_id: Mapped[str] = mapped_column(String(200), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    data: Mapped[JsonObject] = mapped_column(JSON_DOCUMENT, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ImmutableApprovalRecordError(RuntimeError):
    """Raised when code attempts to alter an approval decision or event."""


@event.listens_for(ApprovalDecisionRecord, "before_update")
@event.listens_for(ApprovalDecisionRecord, "before_delete")
@event.listens_for(ApprovalEventRecord, "before_update")
@event.listens_for(ApprovalEventRecord, "before_delete")
def prevent_approval_audit_mutation(
    _mapper: Mapper[Any],
    _connection: Connection,
    _target: ApprovalDecisionRecord | ApprovalEventRecord,
) -> None:
    raise ImmutableApprovalRecordError("Approval decisions and events are append-only")


class SQLAlchemyApprovalRepository:
    """SQLAlchemy implementation of approval persistence."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, approval: ApprovalRequest, audit_event: ApprovalEvent) -> None:
        self._session.add(self._request_record(approval))
        await self._session.flush()
        self._session.add(self._event_record(audit_event))

    async def get(
        self, workspace_id: UUID, approval_id: UUID, *, for_update: bool = False
    ) -> ApprovalRequest | None:
        statement = select(ApprovalRequestRecord).where(
            ApprovalRequestRecord.workspace_id == workspace_id,
            ApprovalRequestRecord.id == approval_id,
        )
        if for_update:
            statement = statement.with_for_update()
        record = (await self._session.execute(statement)).scalar_one_or_none()
        return await self._request_domain(record) if record is not None else None

    async def list(
        self,
        workspace_id: UUID,
        *,
        status: ApprovalStatus | None,
        workflow_id: UUID | None,
        limit: int,
        offset: int,
    ) -> Sequence[ApprovalRequest]:
        statement = select(ApprovalRequestRecord).where(
            ApprovalRequestRecord.workspace_id == workspace_id
        )
        if status is not None:
            statement = statement.where(ApprovalRequestRecord.status == status)
        if workflow_id is not None:
            statement = statement.where(ApprovalRequestRecord.workflow_id == workflow_id)
        records = (
            (
                await self._session.execute(
                    statement.order_by(
                        ApprovalRequestRecord.updated_at.desc(),
                        ApprovalRequestRecord.id,
                    )
                    .limit(limit)
                    .offset(offset)
                )
            )
            .scalars()
            .all()
        )
        return [await self._request_domain(record) for record in records]

    async def save(self, approval: ApprovalRequest, *, previous_version: int) -> None:
        result = cast(
            CursorResult[Any],
            await self._session.execute(
                update(ApprovalRequestRecord)
                .where(
                    ApprovalRequestRecord.workspace_id == approval.workspace_id,
                    ApprovalRequestRecord.id == approval.id,
                    ApprovalRequestRecord.version == previous_version,
                )
                .values(
                    status=approval.status,
                    version=approval.version,
                    round=approval.round,
                    expires_at=approval.expires_at,
                    updated_at=approval.updated_at,
                    decided_at=approval.decided_at,
                    cancelled_at=approval.cancelled_at,
                )
            ),
        )
        if result.rowcount != 1:
            raise ConcurrentApprovalWrite("Approval changed concurrently; reload and retry")

    async def add_decision(self, decision: ApprovalDecision) -> None:
        self._session.add(self._decision_record(decision))

    async def add_event(self, audit_event: ApprovalEvent) -> None:
        self._session.add(self._event_record(audit_event))

    async def resolve_workflow_step(
        self,
        workspace_id: UUID,
        incident_id: UUID,
        workflow_id: UUID,
        step_key: str,
    ) -> bool:
        result = (
            await self._session.execute(
                select(WorkflowStepRecord.id)
                .join(
                    WorkflowRunRecord,
                    WorkflowRunRecord.id == WorkflowStepRecord.workflow_id,
                )
                .where(
                    WorkflowRunRecord.workspace_id == workspace_id,
                    WorkflowRunRecord.id == workflow_id,
                    WorkflowRunRecord.incident_id == incident_id,
                    WorkflowRunRecord.status == WorkflowStatus.AWAITING_APPROVAL,
                    WorkflowStepRecord.workspace_id == workspace_id,
                    WorkflowStepRecord.step_key == step_key,
                    WorkflowStepRecord.status == WorkflowStepStatus.WAITING_APPROVAL,
                )
            )
        ).scalar_one_or_none()
        return result is not None

    async def get_event_by_idempotency(
        self, workspace_id: UUID, idempotency_key: str
    ) -> ApprovalEvent | None:
        record = (
            await self._session.execute(
                select(ApprovalEventRecord).where(
                    ApprovalEventRecord.workspace_id == workspace_id,
                    ApprovalEventRecord.idempotency_key == idempotency_key,
                )
            )
        ).scalar_one_or_none()
        return self._event_domain(record) if record is not None else None

    async def list_events(
        self, workspace_id: UUID, approval_id: UUID, *, limit: int
    ) -> Sequence[ApprovalEvent]:
        records = (
            (
                await self._session.execute(
                    select(ApprovalEventRecord)
                    .where(
                        ApprovalEventRecord.workspace_id == workspace_id,
                        ApprovalEventRecord.approval_id == approval_id,
                    )
                    .order_by(ApprovalEventRecord.sequence)
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        return [self._event_domain(record) for record in records]

    async def _request_domain(self, record: ApprovalRequestRecord) -> ApprovalRequest:
        decisions = (
            (
                await self._session.execute(
                    select(ApprovalDecisionRecord)
                    .where(
                        ApprovalDecisionRecord.workspace_id == record.workspace_id,
                        ApprovalDecisionRecord.approval_id == record.id,
                    )
                    .order_by(
                        ApprovalDecisionRecord.round,
                        ApprovalDecisionRecord.occurred_at,
                    )
                )
            )
            .scalars()
            .all()
        )
        return ApprovalRequest(
            id=record.id,
            workspace_id=record.workspace_id,
            incident_id=record.incident_id,
            workflow_id=record.workflow_id,
            step_key=record.step_key,
            action_summary=record.action_summary,
            risk=record.risk,
            status=record.status,
            required_approvals=record.required_approvals,
            eligible_roles=tuple(record.eligible_roles),
            version=record.version,
            round=record.round,
            requested_by=record.requested_by,
            expires_at=cast(datetime, _as_utc(record.expires_at)),
            created_at=cast(datetime, _as_utc(record.created_at)),
            updated_at=cast(datetime, _as_utc(record.updated_at)),
            decisions=[self._decision_domain(item) for item in decisions],
            decided_at=_as_utc(record.decided_at),
            cancelled_at=_as_utc(record.cancelled_at),
        )

    @staticmethod
    def _request_record(approval: ApprovalRequest) -> ApprovalRequestRecord:
        return ApprovalRequestRecord(
            id=approval.id,
            workspace_id=approval.workspace_id,
            incident_id=approval.incident_id,
            workflow_id=approval.workflow_id,
            step_key=approval.step_key,
            action_summary=approval.action_summary,
            risk=approval.risk,
            status=approval.status,
            required_approvals=approval.required_approvals,
            eligible_roles=list(approval.eligible_roles),
            version=approval.version,
            round=approval.round,
            requested_by=approval.requested_by,
            expires_at=approval.expires_at,
            created_at=approval.created_at,
            updated_at=approval.updated_at,
            decided_at=approval.decided_at,
            cancelled_at=approval.cancelled_at,
        )

    @staticmethod
    def _decision_record(decision: ApprovalDecision) -> ApprovalDecisionRecord:
        return ApprovalDecisionRecord(
            id=decision.id,
            workspace_id=decision.workspace_id,
            approval_id=decision.approval_id,
            round=decision.round,
            actor_id=decision.actor_id,
            actor_role=decision.actor_role,
            decision=decision.decision,
            reason=decision.reason,
            occurred_at=decision.occurred_at,
        )

    @staticmethod
    def _event_record(audit_event: ApprovalEvent) -> ApprovalEventRecord:
        return ApprovalEventRecord(
            id=audit_event.id,
            workspace_id=audit_event.workspace_id,
            approval_id=audit_event.approval_id,
            sequence=audit_event.sequence,
            event_type=audit_event.event_type,
            actor_id=audit_event.actor_id,
            idempotency_key=audit_event.idempotency_key,
            data=audit_event.data,
            occurred_at=audit_event.occurred_at,
        )

    @staticmethod
    def _decision_domain(record: ApprovalDecisionRecord) -> ApprovalDecision:
        return ApprovalDecision(
            id=record.id,
            workspace_id=record.workspace_id,
            approval_id=record.approval_id,
            round=record.round,
            actor_id=record.actor_id,
            actor_role=record.actor_role,
            decision=record.decision,
            reason=record.reason,
            occurred_at=cast(datetime, _as_utc(record.occurred_at)),
        )

    @staticmethod
    def _event_domain(record: ApprovalEventRecord) -> ApprovalEvent:
        return ApprovalEvent(
            id=record.id,
            workspace_id=record.workspace_id,
            approval_id=record.approval_id,
            sequence=record.sequence,
            event_type=record.event_type,
            actor_id=record.actor_id,
            idempotency_key=record.idempotency_key,
            data=dict(record.data),
            occurred_at=cast(datetime, _as_utc(record.occurred_at)),
        )


class SQLAlchemyApprovalUnitOfWork:
    """Async transaction boundary for approval commands."""

    approvals: ApprovalRepository

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None

    async def __aenter__(self) -> "SQLAlchemyApprovalUnitOfWork":
        self._session = self._session_factory()
        self.approvals = SQLAlchemyApprovalRepository(self._session)
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
            raise ConcurrentApprovalWrite(
                "Approval changed concurrently; reload and retry"
            ) from error
