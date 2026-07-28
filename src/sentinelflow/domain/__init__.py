"""Framework-independent SentinelFlow domain model."""

from sentinelflow.domain.incident import (
    ConcurrentIncidentWrite,
    IdempotencyConflict,
    Incident,
    IncidentError,
    IncidentEvent,
    IncidentEventType,
    IncidentNotFound,
    IncidentSeverity,
    IncidentStatus,
    InvalidIncidentTransition,
    VersionConflict,
)

__all__ = [
    "ConcurrentIncidentWrite",
    "IdempotencyConflict",
    "Incident",
    "IncidentError",
    "IncidentEvent",
    "IncidentEventType",
    "IncidentNotFound",
    "IncidentSeverity",
    "IncidentStatus",
    "InvalidIncidentTransition",
    "VersionConflict",
]
