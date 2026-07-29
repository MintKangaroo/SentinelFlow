"""Safe workflow executors for local dry-run and registered service adapters."""

from collections.abc import Mapping
from typing import cast

from sentinelflow.domain import WorkflowRun, WorkflowStepRun
from sentinelflow.domain.playbook import JsonObject, JsonValue
from sentinelflow.integrations import (
    AdapterRequestContext,
    IntegrationConfigurationError,
)
from sentinelflow.integrations.vendors import SecurityServiceAdapter


class DryRunWorkflowStepExecutor:
    """Return deterministic evidence without producing an external side effect."""

    async def execute(
        self,
        *,
        workflow: WorkflowRun,
        step: WorkflowStepRun,
        idempotency_key: str,
    ) -> JsonObject:
        return {
            "mode": "dry_run",
            "external_side_effect": False,
            "adapter": step.adapter,
            "operation": step.operation,
            "parameters": step.parameters,
            "idempotency_key": idempotency_key,
            "workflow_id": str(workflow.id),
        }

    async def compensate(
        self,
        *,
        workflow: WorkflowRun,
        step: WorkflowStepRun,
        idempotency_key: str,
    ) -> JsonObject:
        return {
            "mode": "dry_run",
            "external_side_effect": False,
            "adapter": step.adapter,
            "operation": step.rollback_operation,
            "parameters": step.rollback_parameters,
            "idempotency_key": idempotency_key,
            "workflow_id": str(workflow.id),
        }


class VendorWorkflowStepExecutor:
    """Route snapshotted operations to an allowlisted vendor adapter registry."""

    def __init__(self, adapters: Mapping[str, SecurityServiceAdapter]) -> None:
        self._adapters = dict(adapters)

    async def execute(
        self,
        *,
        workflow: WorkflowRun,
        step: WorkflowStepRun,
        idempotency_key: str,
    ) -> JsonObject:
        return await self._invoke(
            workflow,
            step,
            adapter_name=step.adapter,
            operation=step.operation,
            parameters=step.parameters,
            idempotency_key=idempotency_key,
        )

    async def compensate(
        self,
        *,
        workflow: WorkflowRun,
        step: WorkflowStepRun,
        idempotency_key: str,
    ) -> JsonObject:
        return await self._invoke(
            workflow,
            step,
            adapter_name=step.adapter,
            operation=step.rollback_operation,
            parameters=step.rollback_parameters,
            idempotency_key=idempotency_key,
        )

    async def aclose(self) -> None:
        for adapter in self._adapters.values():
            await adapter.aclose()

    async def _invoke(
        self,
        workflow: WorkflowRun,
        step: WorkflowStepRun,
        *,
        adapter_name: str | None,
        operation: str | None,
        parameters: JsonObject,
        idempotency_key: str,
    ) -> JsonObject:
        if adapter_name is None or operation is None:
            raise IntegrationConfigurationError("Workflow step has no executable operation")
        adapter = self._adapters.get(adapter_name)
        if adapter is None:
            raise IntegrationConfigurationError(
                f"Workflow adapter {adapter_name} is not registered"
            )
        resolved = cast(dict[str, object], self._resolve(parameters, workflow, step.position))
        return cast(JsonObject, await adapter.execute(
            operation,
            resolved,
            context=AdapterRequestContext(
                workspace_id=workflow.workspace_id,
                idempotency_key=idempotency_key,
            ),
        ))

    def _resolve(
        self,
        value: JsonValue,
        workflow: WorkflowRun,
        position: int,
    ) -> JsonValue:
        if isinstance(value, list):
            return [self._resolve(item, workflow, position) for item in value]
        if isinstance(value, dict):
            if set(value) == {"$ref"}:
                reference = value["$ref"]
                if not isinstance(reference, str):
                    raise IntegrationConfigurationError("Parameter reference must be a string")
                return self._resolve_reference(reference, workflow, position)
            return {
                key: self._resolve(item, workflow, position)
                for key, item in value.items()
            }
        return value

    @staticmethod
    def _resolve_reference(
        reference: str,
        workflow: WorkflowRun,
        position: int,
    ) -> JsonValue:
        parts = reference.split(".")
        if len(parts) < 4 or parts[0] != "steps" or parts[2] != "output":
            raise IntegrationConfigurationError("Parameter reference has an invalid shape")
        source = next(
            (
                step
                for step in workflow.steps
                if step.step_key == parts[1] and step.position < position
            ),
            None,
        )
        if source is None:
            raise IntegrationConfigurationError("Parameter reference is not a prior step")
        current: JsonValue = source.output
        for part in parts[3:]:
            if not isinstance(current, dict) or part not in current:
                raise IntegrationConfigurationError("Parameter reference could not be resolved")
            current = current[part]
        return current
