from uuid import uuid4

import pytest

from sentinelflow.application import WorkflowResultTokenSigner
from sentinelflow.domain import InvalidWorkflowResultToken


def test_result_token_is_scoped_signed_and_expires() -> None:
    current = 1_000.0
    signer = WorkflowResultTokenSigner("x" * 32, clock=lambda: current)
    workspace_id = uuid4()
    workflow_id = uuid4()
    token = signer.issue(
        workspace_id=workspace_id,
        workflow_id=workflow_id,
        step_key="enrich",
        purpose="result",
        ttl_seconds=60,
    )
    signer.verify(
        token,
        workspace_id=workspace_id,
        workflow_id=workflow_id,
        step_key="enrich",
        purpose="result",
    )
    with pytest.raises(InvalidWorkflowResultToken):
        signer.verify(
            token,
            workspace_id=workspace_id,
            workflow_id=workflow_id,
            step_key="other",
            purpose="result",
        )
    expired = WorkflowResultTokenSigner("x" * 32, clock=lambda: current + 61)
    with pytest.raises(InvalidWorkflowResultToken):
        expired.verify(
            token,
            workspace_id=workspace_id,
            workflow_id=workflow_id,
            step_key="enrich",
            purpose="result",
        )
    with pytest.raises(InvalidWorkflowResultToken):
        signer.verify(
            f"{token}tampered",
            workspace_id=workspace_id,
            workflow_id=workflow_id,
            step_key="enrich",
            purpose="result",
        )


def test_result_token_rejects_unsafe_configuration() -> None:
    with pytest.raises(ValueError, match="32 bytes"):
        WorkflowResultTokenSigner("short")
    signer = WorkflowResultTokenSigner("x" * 32)
    with pytest.raises(ValueError, match="TTL"):
        signer.issue(
            workspace_id=uuid4(),
            workflow_id=uuid4(),
            step_key="step",
            purpose="result",
            ttl_seconds=0,
        )
