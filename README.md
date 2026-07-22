# SentinelFlow

SentinelFlow is an AI-native security operations control plane. It coordinates the
detection, analysis, approval, response, validation, and reporting boundaries while
leaving each connected security service responsible for its own internal capabilities.

> Status: Stage 1 platform foundation. Incident workflows and external adapters are
> intentionally not implemented yet.

## Foundation

- FastAPI control API with separate liveness and dependency-readiness probes
- PostgreSQL access through async SQLAlchemy and an Alembic migration baseline
- Redis-backed Celery worker boundary with JSON-only messages
- React and TypeScript web shell served through a hardened nginx configuration
- OpenTelemetry trace export through a local collector
- Reproducible Docker Compose development stack and CI quality gates

## Start the stack

Docker Compose is the supported way to run the complete foundation:

```bash
cp .env.example .env
docker compose up --build
```

Then open:

- Web shell: <http://localhost:3000>
- API metadata: <http://localhost:8000/>
- API docs: <http://localhost:8000/docs>
- Readiness: <http://localhost:8000/api/v1/health/ready>

The values in `.env.example` are local-only placeholders. Change them before using a
shared environment and never store integration credentials in this repository or the
application database.

## Local development

Python 3.12+ and Node.js 20+ are required.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
cd web && npm ci && cd ..
make check
```

Run the API and web development server independently with `make api` and `make web`.
PostgreSQL and Redis connection settings use the `SENTINELFLOW_` environment prefix;
see [.env.example](.env.example).

## Scope boundary

This commit contains no Incident model, playbook, workflow state machine, approval gate,
response action, validation execution, or vendor adapter. Those features belong to later
milestones in [docs/roadmap.md](docs/roadmap.md). The current stack only proves the
process, persistence, coordination, UI, migration, and observability boundaries.

## Security

SentinelFlow is for systems the operator is explicitly authorized to defend and test.
See [SECURITY.md](SECURITY.md) and [docs/threat-model.md](docs/threat-model.md). The project
is licensed under the MIT License.
