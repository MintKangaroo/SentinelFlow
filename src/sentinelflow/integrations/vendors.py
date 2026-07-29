"""Strict operation adapters for the SentinelFlow security-service ecosystem."""

import re
from collections.abc import Mapping

from sentinelflow.integrations.base import RESTAdapter
from sentinelflow.integrations.errors import IntegrationConfigurationError
from sentinelflow.integrations.models import AdapterRequestContext

_OPAQUE_TARGET = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,127}$")
_SENSITIVE_KEYS = frozenset(
    {"authorization", "credential", "password", "secret", "token", "api_key", "private_key"}
)


def _sanitized_output(value: object, *, depth: int = 0) -> object:
    if depth > 5:
        raise IntegrationConfigurationError("integration response nesting is too deep")
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        if len(value) > 4000:
            raise IntegrationConfigurationError("integration response string is too large")
        return value
    if isinstance(value, list):
        if len(value) > 200:
            raise IntegrationConfigurationError("integration response list is too large")
        return [_sanitized_output(item, depth=depth + 1) for item in value]
    if isinstance(value, dict):
        if len(value) > 200:
            raise IntegrationConfigurationError("integration response object is too large")
        result: dict[str, object] = {}
        for raw_key, item in value.items():
            key = str(raw_key)
            if key.lower() in _SENSITIVE_KEYS:
                continue
            result[key] = _sanitized_output(item, depth=depth + 1)
        return result
    raise IntegrationConfigurationError("integration response contains an unsupported value")


class SecurityServiceAdapter(RESTAdapter):
    """Allowlisted operation-to-path mapping over the hardened REST transport."""

    operations: Mapping[str, str] = {}
    target_required: frozenset[str] = frozenset()

    async def execute(
        self,
        operation: str,
        parameters: dict[str, object],
        *,
        context: AdapterRequestContext,
    ) -> dict[str, object]:
        path = self.operations.get(operation)
        if path is None:
            raise IntegrationConfigurationError(
                f"{operation} is not allowed by the {self.service_name} adapter"
            )
        if operation in self.target_required:
            self._validate_target(parameters)
        response = await self.request(
            "POST",
            path,
            context=context,
            json=parameters,
        )
        output = _sanitized_output(response.json())
        if not isinstance(output, dict):
            raise IntegrationConfigurationError("integration response must be a JSON object")
        return output

    @staticmethod
    def _validate_target(parameters: Mapping[str, object]) -> None:
        target = parameters.get("target_ref")
        if not isinstance(target, str) or not _OPAQUE_TARGET.fullmatch(target):
            raise IntegrationConfigurationError(
                "response operations require an approved opaque target_ref"
            )
        lowered = target.lower()
        if "://" in lowered or lowered.startswith(("\\\\", "//")):
            raise IntegrationConfigurationError("target_ref cannot be a network URL")


class ThreatGraphAdapter(SecurityServiceAdapter):
    operations = {
        "assets.enrich": "/v1/assets/enrich",
        "iocs.correlate": "/v1/iocs/correlate",
    }


class RedMindAdapter(SecurityServiceAdapter):
    operations = {
        "investigations.analyze": "/v1/investigations/analyze",
        "actions.propose": "/v1/actions/propose",
    }


class PatchtowerAdapter(SecurityServiceAdapter):
    operations = {
        "endpoint.dry_run": "/v1/actions/dry-run",
        "endpoint.isolate": "/v1/endpoints/isolate",
        "endpoint.release": "/v1/endpoints/release",
        "sessions.revoke": "/v1/sessions/revoke",
    }
    target_required = frozenset(operations)

    async def execute(
        self,
        operation: str,
        parameters: dict[str, object],
        *,
        context: AdapterRequestContext,
    ) -> dict[str, object]:
        if operation in {"endpoint.isolate", "sessions.revoke"}:
            preview = await super().execute(
                "endpoint.dry_run",
                parameters,
                context=AdapterRequestContext(
                    workspace_id=context.workspace_id,
                    correlation_id=context.correlation_id,
                    idempotency_key=f"{context.idempotency_key}:dry-run",
                ),
            )
            if preview.get("allowed") is not True:
                raise IntegrationConfigurationError("Patchtower dry-run did not authorize action")
            parameters = {**parameters, "dry_run_receipt": preview.get("receipt")}
        return await super().execute(operation, parameters, context=context)


class AutoPentestAdapter(SecurityServiceAdapter):
    operations = {"endpoint.validate": "/v1/validations/attack-path"}
    target_required = frozenset(operations)

    @staticmethod
    def _validate_target(parameters: Mapping[str, object]) -> None:
        SecurityServiceAdapter._validate_target(parameters)
        authorization = parameters.get("authorization_ref")
        if not isinstance(authorization, str) or not _OPAQUE_TARGET.fullmatch(authorization):
            raise IntegrationConfigurationError("AutoPentest requires an opaque authorization_ref")


class AIShieldAdapter(SecurityServiceAdapter):
    operations = {"model.assess": "/v1/assessments/robustness"}
    target_required = frozenset(operations)


class AISOCAdapter(SecurityServiceAdapter):
    operations = {
        "alerts.acknowledge": "/v1/alerts/acknowledge",
        "alerts.status": "/v1/alerts/status",
    }
