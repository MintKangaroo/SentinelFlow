# API

The API exposes platform health, workspace-scoped Incident lifecycle and Timeline operations,
immutable versioned response Playbooks, and auditable Workflow execution state. It does not
yet ingest external alerts or dispatch response actions to Vendor Adapters.

## Required headers

Every domain endpoint requires `X-Workspace-ID` as a UUID. Write endpoints additionally
require `X-Actor-ID` and `Idempotency-Key`. Workspace context is taken only from the header,
never from the request body.

| Header | Scope | Purpose |
| --- | --- | --- |
| `X-Workspace-ID` | All domain requests | Mandatory tenant boundary |
| `X-Actor-ID` | All domain writes | Audit attribution |
| `Idempotency-Key` | All domain writes | Prevent duplicate mutations |

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
| `POST` | `/api/v1/playbooks` | Create a Playbook and immutable revision one |
| `GET` | `/api/v1/playbooks` | List Playbooks with optional status filtering |
| `GET` | `/api/v1/playbooks/{id}` | Get one Playbook aggregate |
| `POST` | `/api/v1/playbooks/{id}/versions` | Append an immutable revision |
| `GET` | `/api/v1/playbooks/{id}/versions` | List revisions newest first |
| `GET` | `/api/v1/playbooks/{id}/versions/{number}` | Get one content-addressed revision |
| `POST` | `/api/v1/playbooks/{id}/versions/{number}/publish` | Activate one revision |
| `POST` | `/api/v1/playbooks/{id}/archive` | Make a Playbook permanently read-only |
| `GET` | `/api/v1/playbooks/{id}/events` | Read the append-only change history |
| `POST` | `/api/v1/workflows` | Snapshot a Playbook revision into a pending Workflow Run |
| `GET` | `/api/v1/workflows` | List Runs with optional status filtering |
| `GET` | `/api/v1/workflows/{id}` | Get a Run and its ordered Step state |
| `POST` | `/api/v1/workflows/{id}/start` | Start a pending Run |
| `POST` | `/api/v1/workflows/{id}/cancel` | Request cancellation and compensation |
| `POST` | `/api/v1/workflows/{id}/steps/{key}/result` | Record one Step success or failure |
| `POST` | `/api/v1/workflows/{id}/steps/{key}/retry` | Retry a failed Step within its attempt budget |
| `POST` | `/api/v1/workflows/{id}/steps/{key}/approval` | Record the decision at an Approval Step |
| `POST` | `/api/v1/workflows/{id}/steps/{key}/compensation` | Record a compensation result |
| `POST` | `/api/v1/workflows/{id}/steps/{key}/timeout` | Record an active Step timeout |
| `GET` | `/api/v1/workflows/{id}/events` | Read the append-only execution history |
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

A lifecycle transition only records Incident control-plane state. Workflow Approval is a
separate execution gate, and Vendor-side action dispatch remains a later integration milestone.

## Playbook definition rules

Playbook revisions contain 1–50 ordered Typed Steps. Step keys are unique stable identifiers,
and adapter/operation references use a restricted non-executable syntax.

- Supported kinds: `enrichment`, `approval`, `action`, `validation`, `notification`
- Supported risk: `low`, `medium`, `high`, `critical`
- `high` and `critical` Action Steps require an earlier Approval Step.
- `high` and `critical` Action Steps require an explicit `compensate` or `restore` rollback.
- Conditions use a small declarative operator set; arbitrary expressions are not accepted.
- Each revision stores a SHA-256 hash over canonical step JSON.
- Revision and Event records are append-only at ORM and PostgreSQL Trigger levels.

Publishing changes only the active revision pointer. It never mutates revision content.

## Workflow execution rules

A Workflow Run snapshots one specific Playbook revision. Its `playbook_version_id`,
`playbook_version`, Definition Hash, and ordered Step execution metadata never follow a later
Publish operation.

- Runs use explicit states: `pending`, `running`, `awaiting_approval`, `compensating`,
  `succeeded`, `failed`, and `cancelled`.
- Only the current Step may accept a result, approval, timeout, retry, or compensation result.
- Failed Steps require an explicit Retry and cannot exceed three attempts.
- Approval Steps pause the Run until an Actor records a decision.
- Failed or cancelled Runs compensate completed rollback-capable Action Steps in reverse order.
- Every mutation requires `expected_version`; every resulting Event is workspace-scoped,
  sequenced, and append-only.
- A replayed Idempotency Key returns the original result only for the same operation.

These endpoints record durable orchestration state. A worker must call the appropriate Vendor
Adapter and submit the outcome through the Step result endpoints; the current milestone does
not itself perform external actions.
