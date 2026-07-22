# Threat Model

## Assets

Future assets include workspace data, alerts, incident evidence, approval decisions,
action inputs and outputs, audit events, reports, authorization scope, and opaque
integration credential references. PostgreSQL and telemetry may both contain operational
metadata and must be protected accordingly.

## Stage 2 trust boundaries

- All browser and API input is untrusted.
- PostgreSQL and Redis are separate network dependencies.
- Celery messages must use JSON; pickle and other executable serializers are rejected.
- OTLP export crosses a process boundary and is disabled by default outside Compose.
- Container images and npm/Python dependencies are supply-chain inputs.
- Workspace and actor headers are untrusted until bound by an identity gateway.
- Incident titles, descriptions, notes, IDs, and event data are untrusted input.

## Foundation controls

- Production API documentation is disabled.
- CORS permits explicit origins, safe methods, and a minimal header set.
- nginx adds content-type, framing, referrer, and content-security headers.
- Readiness errors expose dependency state but not raw exceptions or connection strings.
- Connection strings use secret-aware configuration types.
- Services run as an unprivileged user where the base image permits it.
- CI has read-only repository permissions and checks backend and frontend code.

## Incident controls

- Every Incident query includes an explicit UUID workspace scope.
- Event foreign keys bind both Incident ID and workspace ID.
- Writes require actor attribution and a workspace-unique idempotency key.
- Optimistic aggregate versions reject stale concurrent mutations.
- Timeline update/delete operations are rejected by ORM hooks and a PostgreSQL trigger.
- Cross-workspace and unknown Incident lookups share one sanitized `404` response.

Workspace headers are isolation context, not authentication. Until a trusted identity gateway
binds authenticated principals to permitted workspaces, the API must not be exposed directly to
untrusted clients.

## Required controls for later milestones

Before external adapters or actions ship, SentinelFlow must add a secret-manager adapter,
signed request verification, webhook replay prevention, identity-bound workspace authorization,
global audit events, mandatory dry-runs, rollback/compensation, approval
expiration, and risk-triggered reapproval. No high-risk action may execute solely from an
AI decision.

AutoPentest use is restricted to owned systems and explicitly authorized targets. Public
internet discovery, credential theft, persistence, evasion, malware deployment, data
destruction, and exfiltration remain outside project scope.
