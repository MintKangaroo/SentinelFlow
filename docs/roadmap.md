# Roadmap

- [x] **Platform initialization** — API, worker, persistence, web, observability, Compose.
- [x] **Incident and timeline** — lifecycle and append-only incident events.
- [x] **Integration Adapter SDK** — auth, retry, timeout, circuit breaker, secret references.
- [ ] **Playbook model** — versions, typed steps, conditions, and rollback definitions.
- [ ] **Workflow engine** — explicit state machine, retries, timeout, cancellation, compensation.
- [ ] **Human approval** — risk-based gates, multiple approvers, and expiration.
- [ ] **Detection and graph integrations** — AI-SOC alert ingest and ThreatGraph enrichment.
- [ ] **RedMind integration** — analysis, proposed actions, and evidence.
- [ ] **Patchtower response** — dry-run, approval, execution, and rollback.
- [ ] **AutoPentest validation** — authorized post-response attack-path verification.
- [ ] **AIShield integration** — robustness assessment for AI-service incidents.
- [ ] **Operations dashboard** — queues, SLA, metrics, timelines, approvals, and audit views.
- [ ] **Integrated demo** — end-to-end mock incident response and report.

Stage 3 is implemented on its feature branch. Each later milestone starts from the latest
`develop` only after its predecessor has been implemented, tested, documented, and reviewed
through the branch workflow.
