"""Short-lived HMAC authentication for workflow result submissions."""

import base64
import json
import time
from collections.abc import Callable
from hashlib import sha256
from hmac import compare_digest
from hmac import new as new_hmac
from uuid import UUID

from sentinelflow.domain import InvalidWorkflowResultToken


class WorkflowResultTokenSigner:
    """Issue and verify scoped, short-lived tokens without persisting raw secrets."""

    def __init__(
        self,
        signing_key: str,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if len(signing_key.encode()) < 32:
            raise ValueError("Workflow result signing key must contain at least 32 bytes")
        self._key = signing_key.encode()
        self._clock = clock

    def issue(
        self,
        *,
        workspace_id: UUID,
        workflow_id: UUID,
        step_key: str,
        purpose: str,
        ttl_seconds: int = 900,
    ) -> str:
        if not 1 <= ttl_seconds <= 3600:
            raise ValueError("Workflow result token TTL must be between 1 and 3600 seconds")
        payload = {
            "exp": int(self._clock()) + ttl_seconds,
            "purpose": purpose,
            "step_key": step_key,
            "workflow_id": str(workflow_id),
            "workspace_id": str(workspace_id),
        }
        encoded = self._encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
        signature = self._encode(new_hmac(self._key, encoded.encode(), sha256).digest())
        return f"{encoded}.{signature}"

    def verify(
        self,
        token: str,
        *,
        workspace_id: UUID,
        workflow_id: UUID,
        step_key: str,
        purpose: str,
    ) -> None:
        try:
            encoded, signature = token.split(".", 1)
            expected = self._encode(new_hmac(self._key, encoded.encode(), sha256).digest())
            if not compare_digest(signature, expected):
                raise InvalidWorkflowResultToken
            payload = json.loads(self._decode(encoded))
            valid = (
                isinstance(payload, dict)
                and payload.get("workspace_id") == str(workspace_id)
                and payload.get("workflow_id") == str(workflow_id)
                and payload.get("step_key") == step_key
                and payload.get("purpose") == purpose
                and isinstance(payload.get("exp"), int)
                and payload["exp"] >= int(self._clock())
            )
            if not valid:
                raise InvalidWorkflowResultToken
        except (ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError):
            raise InvalidWorkflowResultToken from None

    @staticmethod
    def _encode(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).rstrip(b"=").decode()

    @staticmethod
    def _decode(value: str) -> str:
        padding = "=" * (-len(value) % 4)
        return base64.urlsafe_b64decode(value + padding).decode()
