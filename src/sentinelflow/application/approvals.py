"""Application service for risk-based, multi-actor approval requests."""

from collections.abc import Callable, Sequence
from datetime import datetime
from uuid import UUID, uuid4

from sentinelflow.application.incidents import utc_now
from sentinelflow.application.ports import ApprovalUnitOfWork
from sentinelflow.domain import (
    ApprovalDecisionValue,
    ApprovalDependencyNotFound,
    ApprovalEvent,
    ApprovalEventType,
    ApprovalIdempotencyConflict,
    ApprovalNotFound,
    ApprovalRequest,
    ApprovalStatus,
    PlaybookStepRisk,
)
from sentinelflow.domain.playbook import JsonObject

type ApprovalUnitOfWorkFactory = Callable[[], ApprovalUnitOfWork]
type Clock = Callable[[], datetime]
type IdFactory = Callable[[], UUID]
type ApprovalMutation = Callable[[ApprovalRequest, datetime], None]


class ApprovalService:
    """Persist approval quorum decisions behind one workspace-scoped aggregate."""

    def __init__(
        self,
        unit_of_work_factory: ApprovalUnitOfWorkFactory,
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
        incident_id: UUID,
        workflow_id: UUID,
        step_key: str,
        action_summary: str,
        risk: PlaybookStepRisk,
        required_approvals: int,
        eligible_roles: tuple[str, ...],
        expires_at: datetime,
        actor_id: str,
        idempotency_key: str,
    ) -> ApprovalRequest:
        data: JsonObject = {
            "incident_id": str(incident_id),
            "workflow_id": str(workflow_id),
            "step_key": step_key,
            "action_summary": action_summary,
            "risk": risk.value,
            "required_approvals": required_approvals,
            "eligible_roles": list(eligible_roles),
            "expires_at": expires_at.isoformat(),
        }
        async with self._unit_of_work_factory() as unit_of_work:
            replay = await unit_of_work.approvals.get_event_by_idempotency(
                workspace_id, idempotency_key
            )
            if replay is not None:
                self._assert_replay(replay, ApprovalEventType.CREATED, actor_id, data)
                approval = await unit_of_work.approvals.get(workspace_id, replay.approval_id)
                if approval is None:
                    raise ApprovalNotFound
                return approval
            if not await unit_of_work.approvals.resolve_workflow_step(
                workspace_id, incident_id, workflow_id, step_key
            ):
                raise ApprovalDependencyNotFound
            now = self._clock()
            approval = ApprovalRequest(
                id=self._id_factory(),
                workspace_id=workspace_id,
                incident_id=incident_id,
                workflow_id=workflow_id,
                step_key=step_key,
                action_summary=action_summary,
                risk=risk,
                status=ApprovalStatus.PENDING,
                required_approvals=required_approvals,
                eligible_roles=eligible_roles,
                version=1,
                round=1,
                requested_by=actor_id,
                expires_at=expires_at,
                created_at=now,
                updated_at=now,
            )
            event = self._event(
                approval,
                ApprovalEventType.CREATED,
                actor_id,
                idempotency_key,
                data,
                now,
            )
            await unit_of_work.approvals.add(approval, event)
            await unit_of_work.commit()
            return approval

    async def get(self, *, workspace_id: UUID, approval_id: UUID) -> ApprovalRequest:
        async with self._unit_of_work_factory() as unit_of_work:
            approval = await unit_of_work.approvals.get(workspace_id, approval_id)
            if approval is None:
                raise ApprovalNotFound
            return approval

    async def list(
        self,
        *,
        workspace_id: UUID,
        status: ApprovalStatus | None,
        workflow_id: UUID | None,
        limit: int,
        offset: int,
    ) -> Sequence[ApprovalRequest]:
        async with self._unit_of_work_factory() as unit_of_work:
            return await unit_of_work.approvals.list(
                workspace_id,
                status=status,
                workflow_id=workflow_id,
                limit=limit,
                offset=offset,
            )

    async def decide(
        self,
        *,
        workspace_id: UUID,
        approval_id: UUID,
        decision: ApprovalDecisionValue,
        actor_role: str,
        reason: str,
        expected_version: int,
        actor_id: str,
        idempotency_key: str,
    ) -> ApprovalRequest:
        data: JsonObject = {
            "decision": decision.value,
            "actor_role": actor_role,
            "reason": reason,
            "expected_version": expected_version,
        }
        async with self._unit_of_work_factory() as unit_of_work:
            replay = await unit_of_work.approvals.get_event_by_idempotency(
                workspace_id, idempotency_key
            )
            if replay is not None:
                self._assert_replay(
                    replay,
                    ApprovalEventType.DECISION_RECORDED,
                    actor_id,
                    data,
                    approval_id,
                    expected_version,
                )
                approval = await unit_of_work.approvals.get(workspace_id, approval_id)
                if approval is None:
                    raise ApprovalNotFound
                return approval
            approval = await unit_of_work.approvals.get(workspace_id, approval_id, for_update=True)
            if approval is None:
                raise ApprovalNotFound
            previous_version = approval.version
            now = self._clock()
            record = approval.decide(
                decision_id=self._id_factory(),
                actor_id=actor_id,
                actor_role=actor_role,
                decision=decision,
                reason=reason,
                occurred_at=now,
                expected_version=expected_version,
            )
            event = self._event(
                approval,
                ApprovalEventType.DECISION_RECORDED,
                actor_id,
                idempotency_key,
                data,
                now,
            )
            await unit_of_work.approvals.save(approval, previous_version=previous_version)
            await unit_of_work.approvals.add_decision(record)
            await unit_of_work.approvals.add_event(event)
            await unit_of_work.commit()
            return approval

    async def expire(
        self,
        *,
        workspace_id: UUID,
        approval_id: UUID,
        expected_version: int,
        actor_id: str,
        idempotency_key: str,
    ) -> ApprovalRequest:
        return await self._mutate(
            workspace_id,
            approval_id,
            expected_version,
            actor_id,
            idempotency_key,
            ApprovalEventType.EXPIRED,
            {"expected_version": expected_version},
            lambda approval, now: approval.expire(now, expected_version),
        )

    async def renew(
        self,
        *,
        workspace_id: UUID,
        approval_id: UUID,
        expires_at: datetime,
        reason: str,
        expected_version: int,
        actor_id: str,
        idempotency_key: str,
    ) -> ApprovalRequest:
        return await self._mutate(
            workspace_id,
            approval_id,
            expected_version,
            actor_id,
            idempotency_key,
            ApprovalEventType.RENEWED,
            {
                "expected_version": expected_version,
                "expires_at": expires_at.isoformat(),
                "reason": reason,
            },
            lambda approval, now: approval.renew(
                expires_at=expires_at,
                occurred_at=now,
                expected_version=expected_version,
            ),
        )

    async def cancel(
        self,
        *,
        workspace_id: UUID,
        approval_id: UUID,
        expected_version: int,
        actor_id: str,
        idempotency_key: str,
    ) -> ApprovalRequest:
        return await self._mutate(
            workspace_id,
            approval_id,
            expected_version,
            actor_id,
            idempotency_key,
            ApprovalEventType.CANCELLED,
            {"expected_version": expected_version},
            lambda approval, now: approval.cancel(now, expected_version),
        )

    async def events(
        self, *, workspace_id: UUID, approval_id: UUID, limit: int
    ) -> Sequence[ApprovalEvent]:
        await self.get(workspace_id=workspace_id, approval_id=approval_id)
        async with self._unit_of_work_factory() as unit_of_work:
            return await unit_of_work.approvals.list_events(workspace_id, approval_id, limit=limit)

    async def _mutate(
        self,
        workspace_id: UUID,
        approval_id: UUID,
        expected_version: int,
        actor_id: str,
        idempotency_key: str,
        event_type: ApprovalEventType,
        data: JsonObject,
        mutation: ApprovalMutation,
    ) -> ApprovalRequest:
        async with self._unit_of_work_factory() as unit_of_work:
            replay = await unit_of_work.approvals.get_event_by_idempotency(
                workspace_id, idempotency_key
            )
            if replay is not None:
                self._assert_replay(
                    replay,
                    event_type,
                    actor_id,
                    data,
                    approval_id,
                    expected_version,
                )
                approval = await unit_of_work.approvals.get(workspace_id, approval_id)
                if approval is None:
                    raise ApprovalNotFound
                return approval
            approval = await unit_of_work.approvals.get(workspace_id, approval_id, for_update=True)
            if approval is None:
                raise ApprovalNotFound
            previous_version = approval.version
            now = self._clock()
            mutation(approval, now)
            event = self._event(approval, event_type, actor_id, idempotency_key, data, now)
            await unit_of_work.approvals.save(approval, previous_version=previous_version)
            await unit_of_work.approvals.add_event(event)
            await unit_of_work.commit()
            return approval

    def _event(
        self,
        approval: ApprovalRequest,
        event_type: ApprovalEventType,
        actor_id: str,
        idempotency_key: str,
        data: JsonObject,
        occurred_at: datetime,
    ) -> ApprovalEvent:
        return ApprovalEvent(
            id=self._id_factory(),
            workspace_id=approval.workspace_id,
            approval_id=approval.id,
            sequence=approval.version,
            event_type=event_type,
            actor_id=actor_id,
            idempotency_key=idempotency_key,
            data=data,
            occurred_at=occurred_at,
        )

    @staticmethod
    def _assert_replay(
        event: ApprovalEvent,
        event_type: ApprovalEventType,
        actor_id: str,
        data: JsonObject,
        approval_id: UUID | None = None,
        expected_version: int | None = None,
    ) -> None:
        if (
            event.event_type is not event_type
            or event.actor_id != actor_id
            or event.data != data
            or (approval_id is not None and event.approval_id != approval_id)
            or (expected_version is not None and event.sequence != expected_version + 1)
        ):
            raise ApprovalIdempotencyConflict(
                "Idempotency key was already used for a different approval operation"
            )
