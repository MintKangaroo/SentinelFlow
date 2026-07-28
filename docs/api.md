# API

The Stage 2 API exposes platform health plus workspace-scoped Incident lifecycle and
Timeline operations. It does not ingest alerts or execute response actions.

## Required headers

Every Incident endpoint requires `X-Workspace-ID` as a UUID. Write endpoints additionally
require `X-Actor-ID` and `Idempotency-Key`. Workspace context is taken only from the header,
never from the request body.

| Header | Scope | Purpose |
| --- | --- | --- |
| `X-Workspace-ID` | All Incident requests | Mandatory tenant boundary |
| `X-Actor-ID` | Incident writes | Timeline attribution |
| `Idempotency-Key` | Incident writes | Prevent duplicate mutations |

The current milestone does not authenticate these headers. Deploy behind a trusted identity
gateway and never expose the API directly to an untrusted network.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/` | Service name, version, and environment |
| `GET` | `/api/v1/health/live` | Process liveness without dependency access |
| `GET` | `/api/v1/health/ready` | Sanitized PostgreSQL and Redis readiness |
| `POST` | `/api/v1/incidents` | Create an Incident and initial Timeline event |
| `GET` | `/api/v1/incidents` | List workspace Incidents with status filtering |
| `GET` | `/api/v1/incidents/{id}` | Get one workspace Incident |
| `POST` | `/api/v1/incidents/{id}/transitions` | Apply one explicit state edge |
| `POST` | `/api/v1/incidents/{id}/notes` | Append an operator note |
| `GET` | `/api/v1/incidents/{id}/timeline` | Read Timeline events by sequence cursor |
| `GET` | `/docs` | OpenAPI UI outside production |

Mutations require `expected_version`. A stale version, an invalid lifecycle edge, or an
idempotency-key conflict returns HTTP `409` with a stable error code. Looking up an Incident
through another workspace returns the same HTTP `404` response as an unknown ID.

## Lifecycle

```text
new ──> triaging ──> investigating ──> awaiting_approval ──> responding
 │          │               │                  │                   │
 └─> closed └─> resolved    └─> resolved       └─> investigating   └─> validating
                 │                                  responding <───────┘
                 ├─> closed                              │
                 └─> reopened ──> triaging      validating ──> resolved

closed ──> reopened
```

A lifecycle transition only records control-plane state. It does not approve or execute a
response action; those controls belong to later Approval and Workflow milestones.
