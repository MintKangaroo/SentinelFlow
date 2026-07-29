"""Application service for auditable workflow state transitions."""

from collections.abc import Callable, Sequence
from datetime import datetime
from uuid import UUID, uuid4

from sentinelflow.application.incidents import utc_now
from sentinelflow.application.ports import WorkflowUnitOfWork
from sentinelflow.domain import (
    WorkflowDependencyNotFound,
    WorkflowEvent,
    WorkflowEventType,
    WorkflowIdempotencyConflict,
    WorkflowNotFound,
    WorkflowRun,
    WorkflowStatus,
    WorkflowStepRun,
)
from sentinelflow.domain.playbook import JsonObject

type WorkflowUnitOfWorkFactory = Callable[[], WorkflowUnitOfWork]
type Clock = Callable[[], datetime]
type IdFactory = Callable[[], UUID]
type WorkflowMutation = Callable[[WorkflowRun, datetime], None]


class WorkflowService:
    """Create workflow snapshots and record every state-changing decision."""

    def __init__(
        self,
        unit_of_work_factory: WorkflowUnitOfWorkFactory,
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
        playbook_id: UUID,
        playbook_version: int,
        actor_id: str,
        idempotency_key: str,
    ) -> WorkflowRun:
        """Snapshot one immutable playbook revision into a pending run."""
        async with self._unit_of_work_factory() as unit_of_work:
            existing = await unit_of_work.workflows.get_event_by_idempotency(
                workspace_id, idempotency_key
            )
            if existing is not None:
                data: JsonObject = {
                    "incident_id": str(incident_id),
                    "playbook_id": str(playbook_id),
                    "playbook_version": playbook_version,
                }
                self._assert_replay(
                    existing,
                    event_type=WorkflowEventType.CREATED,
                    actor_id=actor_id,
                    data=data,
                )
                workflow = await unit_of_work.workflows.get(workspace_id, existing.workflow_id)
                if workflow is None:
                    raise WorkflowNotFound
                return workflow

            revision = await unit_of_work.workflows.resolve_dependencies(
                workspace_id,
                incident_id,
                playbook_id,
                playbook_version,
            )
            if revision is None:
                raise WorkflowDependencyNotFound
            now = self._clock()
            workflow_id = self._id_factory()
            steps = [
                WorkflowStepRun(
                    id=self._id_factory(),
                    workspace_id=workspace_id,
                    workflow_id=workflow_id,
                    position=position,
                    step_key=step.key,
                    name=step.name,
                    kind=step.kind,
                    risk=step.risk,
                    adapter=step.adapter,
                    operation=step.operation,
                    timeout_seconds=step.timeout_seconds,
                    max_attempts=3,
                    rollback_strategy=(
                        step.rollback.strategy if step.rollback is not None else None
                    ),
                    rollback_operation=(
                        step.rollback.operation if step.rollback is not None else None
                    ),
                    parameters=step.parameters,
                    continue_on_failure=step.continue_on_failure,
                    condition=step.condition,
                    rollback_parameters=(
                        step.rollback.parameters if step.rollback is not None else {}
                    ),
                    rollback_timeout_seconds=(
                        step.rollback.timeout_seconds if step.rollback is not None else 300
                    ),
                )
                for position, step in enumerate(revision.steps)
            ]
            workflow = WorkflowRun(
                id=workflow_id,
                workspace_id=workspace_id,
                incident_id=incident_id,
                playbook_id=playbook_id,
                playbook_version_id=revision.id,
                playbook_version=revision.number,
                definition_hash=revision.definition_hash,
                status=WorkflowStatus.PENDING,
                version=1,
                created_by=actor_id,
                created_at=now,
                updated_at=now,
                steps=steps,
            )
            data = {
                "incident_id": str(incident_id),
                "playbook_id": str(playbook_id),
                "playbook_version": playbook_version,
            }
            event = WorkflowEvent(
                id=self._id_factory(),
                workspace_id=workspace_id,
                workflow_id=workflow.id,
                sequence=1,
                event_type=WorkflowEventType.CREATED,
                actor_id=actor_id,
                idempotency_key=idempotency_key,
                data=data,
                occurred_at=now,
            )
            await unit_of_work.workflows.add(workflow, event)
            await unit_of_work.commit()
            return workflow

    async def get(self, *, workspace_id: UUID, workflow_id: UUID) -> WorkflowRun:
        async with self._unit_of_work_factory() as unit_of_work:
            workflow = await unit_of_work.workflows.get(workspace_id, workflow_id)
            if workflow is None:
                raise WorkflowNotFound
            return workflow

    async def list(
        self,
        *,
        workspace_id: UUID,
        status: WorkflowStatus | None,
        limit: int,
        offset: int,
    ) -> Sequence[WorkflowRun]:
        async with self._unit_of_work_factory() as unit_of_work:
            return await unit_of_work.workflows.list(
                workspace_id, status=status, limit=limit, offset=offset
            )

    async def start(
        self,
        *,
        workspace_id: UUID,
        workflow_id: UUID,
        expected_version: int,
        actor_id: str,
        idempotency_key: str,
    ) -> WorkflowRun:
        data: JsonObject = {"expected_version": expected_version}
        return await self._mutate(
            workspace_id=workspace_id,
            workflow_id=workflow_id,
            expected_version=expected_version,
            actor_id=actor_id,
            idempotency_key=idempotency_key,
            event_type=WorkflowEventType.STARTED,
            data=data,
            mutation=lambda workflow, now: workflow.start(now, expected_version),
        )

    async def record_step_result(
        self,
        *,
        workspace_id: UUID,
        workflow_id: UUID,
        step_key: str,
        succeeded: bool,
        output: JsonObject,
        error_code: str | None,
        expected_version: int,
        actor_id: str,
        idempotency_key: str,
        retryable: bool = True,
    ) -> WorkflowRun:
        data: JsonObject = {
            "step_key": step_key,
            "succeeded": succeeded,
            "output": output,
            "error_code": error_code,
            "expected_version": expected_version,
            "retryable": retryable,
        }
        return await self._mutate(
            workspace_id=workspace_id,
            workflow_id=workflow_id,
            expected_version=expected_version,
            actor_id=actor_id,
            idempotency_key=idempotency_key,
            event_type=(
                WorkflowEventType.STEP_SUCCEEDED if succeeded else WorkflowEventType.STEP_FAILED
            ),
            data=data,
            mutation=lambda workflow, now: workflow.record_step_result(
                step_key=step_key,
                succeeded=succeeded,
                output=output,
                error_code=error_code,
                occurred_at=now,
                expected_version=expected_version,
                retryable=retryable,
            ),
        )

    async def retry_step(
        self,
        *,
        workspace_id: UUID,
        workflow_id: UUID,
        step_key: str,
        expected_version: int,
        actor_id: str,
        idempotency_key: str,
    ) -> WorkflowRun:
        data: JsonObject = {
            "step_key": step_key,
            "expected_version": expected_version,
        }
        return await self._mutate(
            workspace_id=workspace_id,
            workflow_id=workflow_id,
            expected_version=expected_version,
            actor_id=actor_id,
            idempotency_key=idempotency_key,
            event_type=WorkflowEventType.STEP_RETRIED,
            data=data,
            mutation=lambda workflow, now: workflow.retry_step(
                step_key=step_key,
                occurred_at=now,
                expected_version=expected_version,
            ),
        )

    async def record_approval(
        self,
        *,
        workspace_id: UUID,
        workflow_id: UUID,
        step_key: str,
        approved: bool,
        expected_version: int,
        actor_id: str,
        idempotency_key: str,
    ) -> WorkflowRun:
        data: JsonObject = {
            "step_key": step_key,
            "approved": approved,
            "expected_version": expected_version,
        }
        return await self._mutate(
            workspace_id=workspace_id,
            workflow_id=workflow_id,
            expected_version=expected_version,
            actor_id=actor_id,
            idempotency_key=idempotency_key,
            event_type=WorkflowEventType.APPROVAL_RECORDED,
            data=data,
            mutation=lambda workflow, now: workflow.record_approval(
                step_key=step_key,
                approved=approved,
                occurred_at=now,
                expected_version=expected_version,
            ),
        )

    async def cancel(
        self,
        *,
        workspace_id: UUID,
        workflow_id: UUID,
        expected_version: int,
        actor_id: str,
        idempotency_key: str,
    ) -> WorkflowRun:
        data: JsonObject = {"expected_version": expected_version}
        return await self._mutate(
            workspace_id=workspace_id,
            workflow_id=workflow_id,
            expected_version=expected_version,
            actor_id=actor_id,
            idempotency_key=idempotency_key,
            event_type=WorkflowEventType.CANCEL_REQUESTED,
            data=data,
            mutation=lambda workflow, now: workflow.request_cancel(now, expected_version),
        )

    async def record_compensation(
        self,
        *,
        workspace_id: UUID,
        workflow_id: UUID,
        step_key: str,
        succeeded: bool,
        error_code: str | None,
        expected_version: int,
        actor_id: str,
        idempotency_key: str,
    ) -> WorkflowRun:
        data: JsonObject = {
            "step_key": step_key,
            "succeeded": succeeded,
            "error_code": error_code,
            "expected_version": expected_version,
        }
        return await self._mutate(
            workspace_id=workspace_id,
            workflow_id=workflow_id,
            expected_version=expected_version,
            actor_id=actor_id,
            idempotency_key=idempotency_key,
            event_type=WorkflowEventType.COMPENSATION_RECORDED,
            data=data,
            mutation=lambda workflow, now: workflow.record_compensation(
                step_key=step_key,
                succeeded=succeeded,
                error_code=error_code,
                occurred_at=now,
                expected_version=expected_version,
            ),
        )

    async def timeout_step(
        self,
        *,
        workspace_id: UUID,
        workflow_id: UUID,
        step_key: str,
        expected_version: int,
        actor_id: str,
        idempotency_key: str,
    ) -> WorkflowRun:
        data: JsonObject = {
            "step_key": step_key,
            "expected_version": expected_version,
        }

        def timeout(workflow: WorkflowRun, now: datetime) -> None:
            active_key = workflow.timeout_current(now, expected_version)
            if active_key != step_key:
                raise WorkflowIdempotencyConflict

        return await self._mutate(
            workspace_id=workspace_id,
            workflow_id=workflow_id,
            expected_version=expected_version,
            actor_id=actor_id,
            idempotency_key=idempotency_key,
            event_type=WorkflowEventType.TIMED_OUT,
            data=data,
            mutation=timeout,
        )

    async def events(
        self, *, workspace_id: UUID, workflow_id: UUID, limit: int
    ) -> Sequence[WorkflowEvent]:
        async with self._unit_of_work_factory() as unit_of_work:
            workflow = await unit_of_work.workflows.get(workspace_id, workflow_id)
            if workflow is None:
                raise WorkflowNotFound
            return await unit_of_work.workflows.list_events(workspace_id, workflow_id, limit=limit)

    async def _mutate(
        self,
        *,
        workspace_id: UUID,
        workflow_id: UUID,
        expected_version: int,
        actor_id: str,
        idempotency_key: str,
        event_type: WorkflowEventType,
        data: JsonObject,
        mutation: WorkflowMutation,
    ) -> WorkflowRun:
        async with self._unit_of_work_factory() as unit_of_work:
            existing = await unit_of_work.workflows.get_event_by_idempotency(
                workspace_id, idempotency_key
            )
            if existing is not None:
                self._assert_replay(
                    existing,
                    event_type=event_type,
                    actor_id=actor_id,
                    data=data,
                    workflow_id=workflow_id,
                    expected_version=expected_version,
                )
                workflow = await unit_of_work.workflows.get(workspace_id, workflow_id)
                if workflow is None:
                    raise WorkflowNotFound
                return workflow

            workflow = await unit_of_work.workflows.get(workspace_id, workflow_id, for_update=True)
            if workflow is None:
                raise WorkflowNotFound
            previous_version = workflow.version
            occurred_at = self._clock()
            mutation(workflow, occurred_at)
            event = WorkflowEvent(
                id=self._id_factory(),
                workspace_id=workspace_id,
                workflow_id=workflow_id,
                sequence=workflow.version,
                event_type=event_type,
                actor_id=actor_id,
                idempotency_key=idempotency_key,
                data=data,
                occurred_at=occurred_at,
            )
            await unit_of_work.workflows.save(workflow, previous_version=previous_version)
            await unit_of_work.workflows.add_event(event)
            await unit_of_work.commit()
            return workflow

    @staticmethod
    def _assert_replay(
        event: WorkflowEvent,
        *,
        event_type: WorkflowEventType,
        actor_id: str,
        data: JsonObject,
        workflow_id: UUID | None = None,
        expected_version: int | None = None,
    ) -> None:
        if (
            event.event_type is not event_type
            or event.actor_id != actor_id
            or event.data != data
            or (workflow_id is not None and event.workflow_id != workflow_id)
            or (expected_version is not None and event.sequence != expected_version + 1)
        ):
            raise WorkflowIdempotencyConflict
