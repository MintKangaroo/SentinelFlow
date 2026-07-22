# API

The Stage 1 API exposes only platform metadata and health probes. It does not accept
alerts or create incidents.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/` | Service name, version, and environment |
| `GET` | `/api/v1/health/live` | Process liveness without dependency access |
| `GET` | `/api/v1/health/ready` | Sanitized PostgreSQL and Redis readiness |
| `GET` | `/docs` | OpenAPI UI in non-production environments |

Readiness returns HTTP `503` with per-dependency `ok` or `error` states when PostgreSQL
or Redis is unavailable. Raw exception messages, connection strings, and credentials are
never included.
