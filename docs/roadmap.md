# Roadmap

- [x] **Platform initialization** — API, worker, persistence, web, observability, Compose.
- [x] **Incident and timeline** — lifecycle and append-only incident events.
- [x] **Integration Adapter SDK** — auth, retry, timeout, circuit breaker, secret references.
- [x] **Playbook model** — immutable versions, typed steps, declarative conditions,
  definition hashes, approval ordering, and rollback definitions.
- [x] **Workflow engine** — immutable revision snapshots, explicit state machine, retries,
  timeout, cancellation, compensation, and append-only execution events.
- [ ] **Workflow dispatch** — Celery delivery, Adapter invocation, result authentication, and
  recovery after worker interruption.
- [ ] **Human approval** — risk-based gates, multiple approvers, and expiration.
- [ ] **Detection and graph integrations** — AI-SOC alert ingest and ThreatGraph enrichment.
- [ ] **RedMind integration** — analysis, proposed actions, and evidence.
- [ ] **Patchtower response** — dry-run, approval, execution, and rollback.
- [ ] **AutoPentest validation** — authorized post-response attack-path verification.
- [ ] **AIShield integration** — robustness assessment for AI-service incidents.
- [x] **Operations dashboard** — incident queue, metrics, timeline inspector, Playbook and
  Workflow inspectors, approval and integration views, live API operations, and deterministic
  demo mode.
- [ ] **Integrated demo** — end-to-end mock incident response and report.

The platform foundation, Incident lifecycle, Adapter SDK, immutable Playbook model, auditable
Workflow state engine, and Operations Dashboard are implemented. External Side Effects remain
disabled until the Worker Dispatcher and Vendor-specific safety controls are connected.
