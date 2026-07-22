# Architecture

## Stage 1 runtime

The foundation establishes independently replaceable process boundaries without adding
security-operation domain behavior.

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

## Package boundaries

- `sentinelflow.api`: HTTP application factory and transport schemas
- `sentinelflow.infrastructure`: PostgreSQL and Redis lifecycle adapters
- `sentinelflow.runtime`: small protocols used to inject runtime dependencies
- `sentinelflow.worker`: Celery bootstrap; domain tasks are deliberately absent
- `migrations`: versioned database schema history
- `web`: React/TypeScript client and nginx runtime
- `deploy`: process entrypoints and OpenTelemetry Collector configuration

Future domain policy must remain independent of FastAPI, SQLAlchemy, Celery, and vendor
SDKs. External security services will be connected through interfaces and adapters rather
than copied into this repository.

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
