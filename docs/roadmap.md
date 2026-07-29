# Roadmap

- [x] **Platform initialization** — API, worker, persistence, web, observability, Compose.
- [x] **Incident and timeline** — lifecycle and append-only incident events.
- [x] **Integration Adapter SDK** — auth, retry, timeout, circuit breaker, secret references.
- [x] **Playbook model** — immutable versions, typed steps, declarative conditions,
  definition hashes, approval ordering, and rollback definitions.
- [x] **Workflow engine** — immutable revision snapshots, explicit state machine, retries,
  timeout, cancellation, compensation, and append-only execution events.
- [x] **Workflow dispatch** — Celery delivery, Adapter invocation, result authentication, and
  recovery after worker interruption.
- [x] **Human approval** — risk-based gates, multiple approvers, and expiration.
- [x] **Detection and graph integrations** — signed AI-SOC alert ingest and ThreatGraph adapter.
- [x] **RedMind integration** — analysis, proposed actions, and sanitized evidence adapter.
- [x] **Patchtower response** — dry-run, approval, execution, and rollback adapter.
- [x] **AutoPentest validation** — authorized post-response attack-path verification adapter.
- [x] **AIShield integration** — robustness assessment adapter.
- [x] **Operations dashboard** — incident queue, metrics, timeline inspector, Playbook and
  Workflow inspectors, approval and integration views, live API operations, and deterministic
  demo mode.
- [x] **Integrated demo** — deterministic dashboard plus incident report projection and digest.

The default local profile remains dry-run, while external side effects require explicit HTTPS
vendor configuration, workspace binding, and secret references. This keeps the reproducible demo
safe while making the production integration boundary executable and auditable.
