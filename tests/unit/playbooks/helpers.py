from sentinelflow.domain import (
    PlaybookStep,
    PlaybookStepKind,
    PlaybookStepRisk,
    RollbackDefinition,
    RollbackStrategy,
)


def safe_response_steps() -> tuple[PlaybookStep, ...]:
    return (
        PlaybookStep(
            key="enrich_asset",
            name="Enrich affected asset",
            kind=PlaybookStepKind.ENRICHMENT,
            risk=PlaybookStepRisk.LOW,
            adapter="threatgraph",
            operation="assets.enrich",
            parameters={"include_neighbors": True},
        ),
        PlaybookStep(
            key="approve_isolation",
            name="Approve endpoint isolation",
            kind=PlaybookStepKind.APPROVAL,
            risk=PlaybookStepRisk.HIGH,
            adapter=None,
            operation=None,
            parameters={"policy": "two_person"},
        ),
        PlaybookStep(
            key="isolate_endpoint",
            name="Isolate affected endpoint",
            kind=PlaybookStepKind.ACTION,
            risk=PlaybookStepRisk.CRITICAL,
            adapter="patchtower",
            operation="endpoint.isolate",
            parameters={"target": "${incident.asset_id}"},
            rollback=RollbackDefinition(
                strategy=RollbackStrategy.COMPENSATE,
                operation="endpoint.release",
                parameters={"target": "${incident.asset_id}"},
            ),
        ),
        PlaybookStep(
            key="validate_containment",
            name="Validate containment",
            kind=PlaybookStepKind.VALIDATION,
            risk=PlaybookStepRisk.LOW,
            adapter="autopentest",
            operation="endpoint.validate",
            parameters={},
        ),
    )


def low_risk_steps() -> tuple[PlaybookStep, ...]:
    return (
        PlaybookStep(
            key="notify_owner",
            name="Notify asset owner",
            kind=PlaybookStepKind.NOTIFICATION,
            risk=PlaybookStepRisk.LOW,
            adapter="notifications",
            operation="message.send",
            parameters={"channel": "security"},
        ),
    )
