# Architecture

## Stage 2 runtime

The foundation establishes independently replaceable process boundaries. Stage 2 adds
framework-independent Incident policy and workspace-scoped persistence.

```text
Browser ──HTTP──> nginx web ──/api──> FastAPI
                                      ├── PostgreSQL (system of record)
                                      ├── Redis (coordination and broker)
                                      └── OTLP ──> OpenTelemetry Collector
Celery worker <──────── Redis ────────┘
```

The API owns request validation and synchronous command/query boundaries. Celery owns
background execution. PostgreSQL is the durable source of truth; Redis must not become a
second system of record. The React application is a client of the API and never connects
directly to infrastructure services.

Incident commands flow inward through these boundaries:

```text
FastAPI schema/header validation
  └─> IncidentService
       └─> Incident aggregate transition policy
       └─> IncidentUnitOfWork port
            └─> SQLAlchemy repository ──> PostgreSQL
```

The service writes the aggregate version and its Timeline event in one transaction. Every
query includes `workspace_id`; the database also uses a composite Incident/Workspace foreign
key for events. A PostgreSQL trigger rejects Timeline updates and deletes.

## Package boundaries

- `sentinelflow.api`: HTTP application factory and transport schemas
- `sentinelflow.domain`: Incident aggregate, statuses, and allowed state edges
- `sentinelflow.application`: use cases and repository/unit-of-work ports
- `sentinelflow.infrastructure`: SQLAlchemy, PostgreSQL, and Redis adapters
- `sentinelflow.runtime`: small protocols used to inject runtime dependencies
- `sentinelflow.worker`: Celery bootstrap; domain tasks are deliberately absent
- `migrations`: versioned database schema history
- `web`: React/TypeScript client and nginx runtime
- `deploy`: process entrypoints and OpenTelemetry Collector configuration

Domain policy remains independent of FastAPI, SQLAlchemy, Celery, and vendor SDKs. External
security services will be connected through interfaces and adapters rather than copied into
this repository.

## Incident consistency

- Aggregate version starts at `1` and advances for every state change or note.
- Clients supply `expected_version`; stale writes fail instead of overwriting newer work.
- Event sequence matches the resulting aggregate version.
- Idempotency keys are unique per workspace and can replay only an identical operation.
- Timeline events have no HTTP update/delete route and are immutable in ORM and PostgreSQL.

## Configuration and secrets

Configuration is loaded from environment variables with the `SENTINELFLOW_` prefix.
Database and Redis URLs use secret-aware types to avoid accidental representation in
logs. Local Compose credentials are replaceable development placeholders.

Integration secrets must never be persisted as plaintext domain data. The Integration
Adapter milestone will introduce opaque `CredentialReference` values and a secret-manager
port. Until that boundary exists, no external integration credential is accepted.

## Observability

OpenTelemetry instrumentation is opt-in outside Compose. Compose enables API tracing and
exports OTLP spans to a collector whose development exporter writes summarized spans.
Production deployments must replace the debug exporter with an approved observability
backend and configure transport security.
