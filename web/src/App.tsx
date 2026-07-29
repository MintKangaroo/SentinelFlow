import { FormEvent, useEffect, useMemo, useState } from "react";

import {
  approveWorkflowStep,
  createIncident,
  fetchIncidents,
  fetchIncidentTimeline,
  fetchPlaybooks,
  fetchPlaybookVersion,
  fetchReadiness,
  fetchWorkflows,
  publishPlaybook,
  startWorkflow,
  transitionIncident,
  type ApiContext,
  type CreateIncidentInput,
  type Incident,
  type IncidentEvent,
  type IncidentSeverity,
  type IncidentStatus,
  type Playbook,
  type PlaybookVersion,
  type Readiness,
  type Workflow,
  type WorkflowStatus,
  type WorkflowStepStatus,
} from "./api";
import "./styles.css";

type View = "overview" | "incidents" | "approvals" | "playbooks" | "workflows" | "integrations";
type IconName =
  | "activity"
  | "alert"
  | "approval"
  | "arrow"
  | "check"
  | "chevron"
  | "clock"
  | "grid"
  | "integration"
  | "menu"
  | "plus"
  | "search"
  | "shield"
  | "spark"
  | "x";

const WORKSPACE: ApiContext = {
  workspaceId: "11111111-1111-4111-8111-111111111111",
  actorId: "security.operator@sentinelflow.local",
};

const DEMO_INCIDENTS: Incident[] = [
  {
    id: "79c95d89-532a-47eb-a023-997864376968",
    workspace_id: WORKSPACE.workspaceId,
    title: "Privilege escalation on production cluster",
    description: "Unusual service-account token exchange followed by cluster-admin binding.",
    severity: "critical",
    status: "responding",
    version: 5,
    created_at: "2026-07-28T02:13:00Z",
    updated_at: "2026-07-28T03:38:00Z",
    resolved_at: null,
    closed_at: null,
  },
  {
    id: "ca29a427-c86f-4592-bd07-e9a055382a88",
    workspace_id: WORKSPACE.workspaceId,
    title: "Suspicious PowerShell beacon detected",
    description: "Encoded command initiated recurring outbound traffic to a newly observed domain.",
    severity: "high",
    status: "awaiting_approval",
    version: 4,
    created_at: "2026-07-28T02:41:00Z",
    updated_at: "2026-07-28T03:31:00Z",
    resolved_at: null,
    closed_at: null,
  },
  {
    id: "f3735250-2dce-4e46-a26d-28006ff48461",
    workspace_id: WORKSPACE.workspaceId,
    title: "Impossible travel sign-in sequence",
    description: "Two successful sign-ins from Seoul and Frankfurt within eleven minutes.",
    severity: "high",
    status: "investigating",
    version: 3,
    created_at: "2026-07-28T02:58:00Z",
    updated_at: "2026-07-28T03:25:00Z",
    resolved_at: null,
    closed_at: null,
  },
  {
    id: "62737394-aa53-4776-8417-22cab75bffeb",
    workspace_id: WORKSPACE.workspaceId,
    title: "Public object storage policy drift",
    description: "Infrastructure policy monitor found anonymous read access on a backup bucket.",
    severity: "medium",
    status: "triaging",
    version: 2,
    created_at: "2026-07-28T03:05:00Z",
    updated_at: "2026-07-28T03:17:00Z",
    resolved_at: null,
    closed_at: null,
  },
  {
    id: "fcfbe947-5f7f-4db2-91bc-bae364771e87",
    workspace_id: WORKSPACE.workspaceId,
    title: "Malicious OAuth application consent",
    description: "User granted mailbox access to an application with a low publisher reputation.",
    severity: "medium",
    status: "validating",
    version: 6,
    created_at: "2026-07-28T01:21:00Z",
    updated_at: "2026-07-28T03:12:00Z",
    resolved_at: null,
    closed_at: null,
  },
  {
    id: "cd18229b-58c7-45fa-bbbc-f4152bb9be48",
    workspace_id: WORKSPACE.workspaceId,
    title: "Container image vulnerability threshold exceeded",
    description: "A deployed workload contains a critical package vulnerability with a public exploit.",
    severity: "low",
    status: "resolved",
    version: 7,
    created_at: "2026-07-28T00:05:00Z",
    updated_at: "2026-07-28T02:55:00Z",
    resolved_at: "2026-07-28T02:55:00Z",
    closed_at: null,
  },
];

const DEMO_TIMELINES: Record<string, IncidentEvent[]> = {
  [DEMO_INCIDENTS[0].id]: [
    {
      id: "d0aa30ce-5cc0-476f-9659-c51ad8d074af",
      incident_id: DEMO_INCIDENTS[0].id,
      sequence: 5,
      event_type: "status_changed",
      actor_id: "workflow@sentinelflow",
      data: { from_status: "awaiting_approval", to_status: "responding", reason: "Response approved by Mina Park" },
      occurred_at: "2026-07-28T03:38:00Z",
    },
    {
      id: "64216942-9fa0-4de5-b26b-d9d43f0fb340",
      incident_id: DEMO_INCIDENTS[0].id,
      sequence: 4,
      event_type: "note_added",
      actor_id: "redmind@adapter",
      data: { body: "Confidence 96%. Recommended action: revoke token and isolate workload." },
      occurred_at: "2026-07-28T03:26:00Z",
    },
    {
      id: "12c14029-c00e-4444-b04a-c61c77d5f83a",
      incident_id: DEMO_INCIDENTS[0].id,
      sequence: 3,
      event_type: "status_changed",
      actor_id: "analyst@sentinelflow",
      data: { from_status: "triaging", to_status: "investigating", reason: "Escalated after graph correlation" },
      occurred_at: "2026-07-28T02:45:00Z",
    },
  ],
};

const DEMO_PLAYBOOKS: Playbook[] = [
  {
    id: "7e784ac0-d1ac-4d95-8b47-8183eb5819c5",
    workspace_id: WORKSPACE.workspaceId,
    name: "Critical endpoint containment",
    description: "Enrich, approve, isolate, and validate a compromised endpoint.",
    status: "active",
    latest_version: 3,
    active_version: 3,
    version: 5,
    created_at: "2026-07-25T03:10:00Z",
    updated_at: "2026-07-28T03:29:00Z",
    archived_at: null,
  },
  {
    id: "94322b16-9e6d-4ae4-bda6-4dfba6e64da8",
    workspace_id: WORKSPACE.workspaceId,
    name: "Suspicious identity response",
    description: "Revoke active sessions and enforce credential rotation.",
    status: "draft",
    latest_version: 2,
    active_version: 1,
    version: 3,
    created_at: "2026-07-26T02:10:00Z",
    updated_at: "2026-07-28T03:04:00Z",
    archived_at: null,
  },
  {
    id: "4bb5f97b-bd76-4385-9834-b608140d1d41",
    workspace_id: WORKSPACE.workspaceId,
    name: "Cloud policy drift remediation",
    description: "Restore a reviewed storage policy and validate external exposure.",
    status: "active",
    latest_version: 1,
    active_version: 1,
    version: 2,
    created_at: "2026-07-27T01:32:00Z",
    updated_at: "2026-07-28T02:42:00Z",
    archived_at: null,
  },
];

const DEMO_PLAYBOOK_VERSION: PlaybookVersion = {
  id: "d96f7789-32e6-4dde-8950-ad8ad9fb64fa",
  workspace_id: WORKSPACE.workspaceId,
  playbook_id: DEMO_PLAYBOOKS[0].id,
  number: 3,
  definition_hash: "5b72d2183d8ad9c86b5a3c79d9802283f4a68e2d1bcf8472c1e388dac2996371",
  created_by: "mina.park@sentinelflow",
  created_at: "2026-07-28T03:29:00Z",
  steps: [
    {
      key: "enrich_asset",
      name: "Enrich affected asset",
      kind: "enrichment",
      risk: "low",
      adapter: "threatgraph",
      operation: "assets.enrich",
      parameters: {},
      timeout_seconds: 120,
      continue_on_failure: false,
      condition: null,
      rollback: null,
    },
    {
      key: "approve_isolation",
      name: "Approve endpoint isolation",
      kind: "approval",
      risk: "high",
      adapter: null,
      operation: null,
      parameters: { policy: "two_person" },
      timeout_seconds: 900,
      continue_on_failure: false,
      condition: null,
      rollback: null,
    },
    {
      key: "isolate_endpoint",
      name: "Isolate affected endpoint",
      kind: "action",
      risk: "critical",
      adapter: "patchtower",
      operation: "endpoint.isolate",
      parameters: {},
      timeout_seconds: 300,
      continue_on_failure: false,
      condition: null,
      rollback: {
        strategy: "compensate",
        operation: "endpoint.release",
        parameters: {},
        timeout_seconds: 300,
      },
    },
    {
      key: "validate_containment",
      name: "Validate containment",
      kind: "validation",
      risk: "low",
      adapter: "autopentest",
      operation: "endpoint.validate",
      parameters: {},
      timeout_seconds: 600,
      continue_on_failure: false,
      condition: null,
      rollback: null,
    },
  ],
};

const DEMO_WORKFLOWS: Workflow[] = [
  {
    id: "22b9197f-61c0-49e8-9fdc-c487b625dd08",
    workspace_id: WORKSPACE.workspaceId,
    incident_id: DEMO_INCIDENTS[1].id,
    playbook_id: DEMO_PLAYBOOKS[0].id,
    playbook_version_id: DEMO_PLAYBOOK_VERSION.id,
    playbook_version: 3,
    definition_hash: DEMO_PLAYBOOK_VERSION.definition_hash,
    status: "awaiting_approval",
    version: 4,
    created_by: "workflow@sentinelflow",
    created_at: "2026-07-28T02:47:00Z",
    updated_at: "2026-07-28T03:31:00Z",
    started_at: "2026-07-28T02:48:00Z",
    finished_at: null,
    cancel_requested: false,
    steps: [
      {
        id: "d1bcfd8e-43a9-4f63-838f-03d9ee598ef8",
        position: 0,
        step_key: "enrich_asset",
        name: "Enrich affected asset",
        kind: "enrichment",
        risk: "low",
        adapter: "threatgraph",
        operation: "assets.enrich",
        timeout_seconds: 120,
        max_attempts: 3,
        rollback_strategy: null,
        rollback_operation: null,
        parameters: {},
        continue_on_failure: false,
        condition: null,
        rollback_parameters: {},
        rollback_timeout_seconds: 300,
        status: "succeeded",
        attempt: 1,
        output: { confidence: 0.96, asset_tier: "production" },
        last_error_code: null,
        started_at: "2026-07-28T02:48:00Z",
        finished_at: "2026-07-28T02:48:31Z",
      },
      {
        id: "7aa628d0-5764-4923-815c-938ae4b9e99f",
        position: 1,
        step_key: "approve_isolation",
        name: "Approve endpoint isolation",
        kind: "approval",
        risk: "high",
        adapter: null,
        operation: null,
        timeout_seconds: 900,
        max_attempts: 1,
        rollback_strategy: null,
        rollback_operation: null,
        parameters: { policy: "two_person" },
        continue_on_failure: false,
        condition: null,
        rollback_parameters: {},
        rollback_timeout_seconds: 300,
        status: "waiting_approval",
        attempt: 1,
        output: {},
        last_error_code: null,
        started_at: "2026-07-28T02:48:31Z",
        finished_at: null,
      },
      {
        id: "4937f9f6-02a3-4f64-a8f4-1431db3a8f45",
        position: 2,
        step_key: "isolate_endpoint",
        name: "Isolate affected endpoint",
        kind: "action",
        risk: "critical",
        adapter: "patchtower",
        operation: "endpoint.isolate",
        timeout_seconds: 300,
        max_attempts: 3,
        rollback_strategy: "compensate",
        rollback_operation: "endpoint.release",
        parameters: {},
        continue_on_failure: false,
        condition: null,
        rollback_parameters: {},
        rollback_timeout_seconds: 300,
        status: "pending",
        attempt: 0,
        output: {},
        last_error_code: null,
        started_at: null,
        finished_at: null,
      },
      {
        id: "37356a09-55cc-4408-b7db-5e56910ab04d",
        position: 3,
        step_key: "validate_containment",
        name: "Validate containment",
        kind: "validation",
        risk: "low",
        adapter: "autopentest",
        operation: "endpoint.validate",
        timeout_seconds: 600,
        max_attempts: 3,
        rollback_strategy: null,
        rollback_operation: null,
        parameters: {},
        continue_on_failure: false,
        condition: null,
        rollback_parameters: {},
        rollback_timeout_seconds: 300,
        status: "pending",
        attempt: 0,
        output: {},
        last_error_code: null,
        started_at: null,
        finished_at: null,
      },
    ],
  },
  {
    id: "4784ad26-3d4f-480f-88d0-a7223367e7cb",
    workspace_id: WORKSPACE.workspaceId,
    incident_id: DEMO_INCIDENTS[0].id,
    playbook_id: DEMO_PLAYBOOKS[0].id,
    playbook_version_id: DEMO_PLAYBOOK_VERSION.id,
    playbook_version: 3,
    definition_hash: DEMO_PLAYBOOK_VERSION.definition_hash,
    status: "running",
    version: 7,
    created_by: "mina.park@sentinelflow",
    created_at: "2026-07-28T02:13:00Z",
    updated_at: "2026-07-28T03:38:00Z",
    started_at: "2026-07-28T02:14:00Z",
    finished_at: null,
    cancel_requested: false,
    steps: [],
  },
  {
    id: "40941c36-c3cc-47e7-afd1-35324d9bb70d",
    workspace_id: WORKSPACE.workspaceId,
    incident_id: DEMO_INCIDENTS[5].id,
    playbook_id: DEMO_PLAYBOOKS[2].id,
    playbook_version_id: "a63197a9-4c88-4071-a363-5002628a9c69",
    playbook_version: 1,
    definition_hash: "de81f770bd5aa2d67bb3768a8f97bf79f01b9112734f448819e818e9ee828867",
    status: "succeeded",
    version: 9,
    created_by: "workflow@sentinelflow",
    created_at: "2026-07-28T00:06:00Z",
    updated_at: "2026-07-28T02:55:00Z",
    started_at: "2026-07-28T00:07:00Z",
    finished_at: "2026-07-28T02:55:00Z",
    cancel_requested: false,
    steps: [],
  },
];

const STATUS_LABELS: Record<IncidentStatus, string> = {
  new: "New",
  triaging: "Triaging",
  investigating: "Investigating",
  awaiting_approval: "Awaiting approval",
  responding: "Responding",
  validating: "Validating",
  resolved: "Resolved",
  closed: "Closed",
  reopened: "Reopened",
};

const WORKFLOW_STATUS_LABELS: Record<WorkflowStatus, string> = {
  pending: "Pending",
  running: "Running",
  awaiting_approval: "Awaiting approval",
  compensating: "Compensating",
  succeeded: "Succeeded",
  failed: "Failed",
  cancelled: "Cancelled",
};

const WORKFLOW_STEP_STATUS_LABELS: Record<WorkflowStepStatus, string> = {
  pending: "Queued",
  running: "Running",
  waiting_approval: "Human review",
  succeeded: "Completed",
  failed: "Failed",
  skipped: "Skipped",
  compensating: "Rolling back",
  compensated: "Compensated",
};

const NEXT_STATUS: Partial<Record<IncidentStatus, IncidentStatus>> = {
  new: "triaging",
  triaging: "investigating",
  investigating: "awaiting_approval",
  awaiting_approval: "responding",
  responding: "validating",
  validating: "resolved",
  resolved: "closed",
  reopened: "triaging",
};

const INTEGRATIONS = [
  { name: "AI-SOC", detail: "Detection ingest", state: "Connected", latency: "32 ms", tone: "cyan" },
  { name: "ThreatGraph", detail: "IOC correlation", state: "Connected", latency: "48 ms", tone: "violet" },
  { name: "RedMind", detail: "AI investigation", state: "Connected", latency: "81 ms", tone: "rose" },
  { name: "Patchtower", detail: "Response actions", state: "Ready", latency: "57 ms", tone: "amber" },
  { name: "AutoPentest", detail: "Post-response validation", state: "Standby", latency: "—", tone: "blue" },
  { name: "AIShield", detail: "Model robustness", state: "Standby", latency: "—", tone: "green" },
];

function Icon({ name, size = 18 }: { name: IconName; size?: number }) {
  const paths: Record<IconName, React.ReactNode> = {
    activity: <><path d="M3 12h3l2-6 4 12 3-8 2 4h4" /></>,
    alert: <><path d="M12 3 2.8 20h18.4L12 3Z" /><path d="M12 9v4" /><path d="M12 17h.01" /></>,
    approval: <><path d="M8 3h8v4H8z" /><path d="M6 5H4v16h16V5h-2" /><path d="m8 14 2.5 2.5L16 11" /></>,
    arrow: <><path d="M5 12h14" /><path d="m14 7 5 5-5 5" /></>,
    check: <><path d="m5 12 4 4L19 6" /></>,
    chevron: <><path d="m9 18 6-6-6-6" /></>,
    clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
    grid: <><rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /><rect x="14" y="14" width="7" height="7" rx="1" /></>,
    integration: <><circle cx="6" cy="12" r="3" /><circle cx="18" cy="6" r="3" /><circle cx="18" cy="18" r="3" /><path d="m8.6 10.5 6.8-3" /><path d="m8.6 13.5 6.8 3" /></>,
    menu: <><path d="M4 7h16" /><path d="M4 12h16" /><path d="M4 17h16" /></>,
    plus: <><path d="M12 5v14" /><path d="M5 12h14" /></>,
    search: <><circle cx="11" cy="11" r="7" /><path d="m20 20-4-4" /></>,
    shield: <><path d="M12 3 5 6v5c0 4.6 2.8 8.2 7 10 4.2-1.8 7-5.4 7-10V6l-7-3Z" /><path d="m9 12 2 2 4-4" /></>,
    spark: <><path d="m12 3 1.2 4.8L18 9l-4.8 1.2L12 15l-1.2-4.8L6 9l4.8-1.2L12 3Z" /><path d="m18.5 15 .6 2.4 2.4.6-2.4.6-.6 2.4-.6-2.4-2.4-.6 2.4-.6.6-2.4Z" /></>,
    x: <><path d="m6 6 12 12" /><path d="m18 6-12 12" /></>,
  };
  return (
    <svg aria-hidden="true" className="icon" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      {paths[name]}
    </svg>
  );
}

function formatRelative(date: string): string {
  const minutes = Math.max(1, Math.round((Date.now() - new Date(date).getTime()) / 60_000));
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

function shortId(id: string): string {
  return `INC-${id.slice(0, 4).toUpperCase()}`;
}

function shortWorkflowId(id: string): string {
  return `RUN-${id.slice(0, 4).toUpperCase()}`;
}

function SeverityBadge({ severity }: { severity: IncidentSeverity }) {
  return <span className={`severity severity-${severity}`}><span />{severity}</span>;
}

function StatusBadge({ status }: { status: IncidentStatus }) {
  return <span className={`status-badge status-${status}`}>{STATUS_LABELS[status]}</span>;
}

function EmptyState({ title, copy }: { title: string; copy: string }) {
  return (
    <div className="empty-state">
      <span className="empty-icon"><Icon name="shield" size={24} /></span>
      <strong>{title}</strong>
      <p>{copy}</p>
    </div>
  );
}

function IncidentTable({
  incidents,
  selectedId,
  onSelect,
}: {
  incidents: Incident[];
  selectedId: string | null;
  onSelect: (incident: Incident) => void;
}) {
  if (!incidents.length) {
    return <EmptyState title="No incidents in this view" copy="Adjust the filters or create a new incident to begin triage." />;
  }
  return (
    <div className="table-scroll">
      <table className="incident-table">
        <thead>
          <tr>
            <th>Incident</th>
            <th>Severity</th>
            <th>Status</th>
            <th>Updated</th>
            <th><span className="sr-only">Open</span></th>
          </tr>
        </thead>
        <tbody>
          {incidents.map((incident) => (
            <tr
              className={selectedId === incident.id ? "selected" : ""}
              key={incident.id}
              onClick={() => onSelect(incident)}
            >
              <td>
                <span className="incident-title">{incident.title}</span>
                <span className="incident-id">{shortId(incident.id)}</span>
              </td>
              <td><SeverityBadge severity={incident.severity} /></td>
              <td><StatusBadge status={incident.status} /></td>
              <td className="updated-cell">{formatRelative(incident.updated_at)}</td>
              <td><Icon name="chevron" size={16} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CreateIncidentModal({
  busy,
  error,
  onClose,
  onCreate,
}: {
  busy: boolean;
  error: string | null;
  onClose: () => void;
  onCreate: (input: CreateIncidentInput) => Promise<void>;
}) {
  const [severity, setSeverity] = useState<IncidentSeverity>("high");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await onCreate({
      title: String(form.get("title") ?? ""),
      description: String(form.get("description") ?? ""),
      severity,
    });
  }

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section className="modal" role="dialog" aria-modal="true" aria-labelledby="create-title">
        <div className="modal-heading">
          <div>
            <p className="eyebrow">NEW CASE</p>
            <h2 id="create-title">Create incident</h2>
          </div>
          <button className="icon-button" type="button" onClick={onClose} aria-label="Close"><Icon name="x" /></button>
        </div>
        <form onSubmit={submit}>
          <label>
            Incident title
            <input name="title" required maxLength={200} placeholder="Describe the detected security event" autoFocus />
          </label>
          <label>
            Description
            <textarea name="description" maxLength={4000} rows={4} placeholder="Add the evidence and context known so far" />
          </label>
          <fieldset>
            <legend>Severity</legend>
            <div className="severity-picker">
              {(["low", "medium", "high", "critical"] as const).map((value) => (
                <button
                  className={severity === value ? `active pick-${value}` : ""}
                  key={value}
                  type="button"
                  onClick={() => setSeverity(value)}
                >
                  {value}
                </button>
              ))}
            </div>
          </fieldset>
          {error && <p className="form-error">{error}</p>}
          <div className="modal-actions">
            <button className="button secondary" type="button" onClick={onClose}>Cancel</button>
            <button className="button primary" type="submit" disabled={busy}>{busy ? "Creating…" : "Create incident"}</button>
          </div>
        </form>
      </section>
    </div>
  );
}

function Timeline({
  incident,
  events,
  busy,
  onAdvance,
}: {
  incident: Incident | null;
  events: IncidentEvent[];
  busy: boolean;
  onAdvance: (incident: Incident) => Promise<void>;
}) {
  if (!incident) {
    return <EmptyState title="Select an incident" copy="Choose a row to inspect its immutable response timeline." />;
  }
  const next = NEXT_STATUS[incident.status];
  return (
    <div className="timeline-content">
      <div className="focus-heading">
        <div>
          <span className="incident-id">{shortId(incident.id)}</span>
          <h3>{incident.title}</h3>
        </div>
        <SeverityBadge severity={incident.severity} />
      </div>
      <p className="focus-description">{incident.description || "No additional description was provided."}</p>
      <div className="response-progress" aria-label="Response progress">
        {["Triage", "Investigate", "Approve", "Respond", "Validate"].map((label, index) => {
          const statusIndex = ["new", "triaging", "investigating", "awaiting_approval", "responding", "validating", "resolved", "closed"].indexOf(incident.status);
          return <span className={index <= Math.max(0, statusIndex - 1) ? "complete" : ""} key={label}><i>{index < statusIndex - 1 ? <Icon name="check" size={11} /> : index + 1}</i>{label}</span>;
        })}
      </div>
      <div className="timeline-list">
        {events.length ? events.slice(0, 4).map((event) => (
          <article key={event.id}>
            <span className={`event-mark event-${event.event_type}`}><Icon name={event.event_type === "note_added" ? "spark" : "activity"} size={14} /></span>
            <div>
              <strong>{event.event_type === "note_added" ? "Evidence added" : event.event_type === "incident_created" ? "Incident created" : "Lifecycle advanced"}</strong>
              <p>{String(event.data.reason ?? event.data.body ?? "Incident registered in the control plane")}</p>
              <small>{event.actor_id} · {formatRelative(event.occurred_at)}</small>
            </div>
          </article>
        )) : (
          <p className="timeline-placeholder">Timeline events will appear here as the response progresses.</p>
        )}
      </div>
      {next && (
        <button className="button primary advance-button" type="button" onClick={() => onAdvance(incident)} disabled={busy}>
          {busy ? "Updating…" : incident.status === "awaiting_approval" ? "Approve response" : `Move to ${STATUS_LABELS[next]}`}
          <Icon name="arrow" size={16} />
        </button>
      )}
    </div>
  );
}

export function App() {
  const queryParameters = new URLSearchParams(window.location.search);
  const demoMode = queryParameters.get("demo") === "1";
  const requestedView = queryParameters.get("view");
  const initialView: View = requestedView === "incidents" || requestedView === "approvals" || requestedView === "playbooks" || requestedView === "workflows" || requestedView === "integrations" ? requestedView : "overview";
  const [view, setView] = useState<View>(initialView);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [readiness, setReadiness] = useState<Readiness | null>(demoMode ? { status: "ready", checks: { database: "ok", redis: "ok", worker: "ok" } } : null);
  const [unavailable, setUnavailable] = useState(false);
  const [incidents, setIncidents] = useState<Incident[]>(demoMode ? DEMO_INCIDENTS : []);
  const [selectedId, setSelectedId] = useState<string | null>(demoMode ? DEMO_INCIDENTS[0].id : null);
  const [events, setEvents] = useState<IncidentEvent[]>(demoMode ? DEMO_TIMELINES[DEMO_INCIDENTS[0].id] : []);
  const [playbooks, setPlaybooks] = useState<Playbook[]>(demoMode ? DEMO_PLAYBOOKS : []);
  const [selectedPlaybookId, setSelectedPlaybookId] = useState<string | null>(demoMode ? DEMO_PLAYBOOKS[0].id : null);
  const [playbookVersion, setPlaybookVersion] = useState<PlaybookVersion | null>(demoMode ? DEMO_PLAYBOOK_VERSION : null);
  const [workflows, setWorkflows] = useState<Workflow[]>(demoMode ? DEMO_WORKFLOWS : []);
  const [selectedWorkflowId, setSelectedWorkflowId] = useState<string | null>(demoMode ? DEMO_WORKFLOWS[0].id : null);
  const [query, setQuery] = useState("");
  const [severityFilter, setSeverityFilter] = useState<IncidentSeverity | "all">("all");
  const [loading, setLoading] = useState(!demoMode);
  const [mutating, setMutating] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (demoMode) return;
    const controller = new AbortController();
    Promise.all([
      fetchReadiness(controller.signal),
      fetchIncidents(WORKSPACE, controller.signal),
      fetchPlaybooks(WORKSPACE, controller.signal),
      fetchWorkflows(WORKSPACE, controller.signal),
    ])
      .then(([health, result, loadedPlaybooks, loadedWorkflows]) => {
        setReadiness(health);
        setIncidents(result);
        setPlaybooks(loadedPlaybooks);
        setWorkflows(loadedWorkflows);
        if (result[0]) setSelectedId(result[0].id);
        if (loadedPlaybooks[0]) setSelectedPlaybookId(loadedPlaybooks[0].id);
        if (loadedWorkflows[0]) setSelectedWorkflowId(loadedWorkflows[0].id);
      })
      .catch((caught: unknown) => {
        if (controller.signal.aborted) return;
        setUnavailable(true);
        setError(caught instanceof Error ? caught.message : "Unable to reach the control plane");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [demoMode]);

  useEffect(() => {
    if (!selectedId) {
      setEvents([]);
      return;
    }
    if (demoMode) {
      setEvents(DEMO_TIMELINES[selectedId] ?? []);
      return;
    }
    const controller = new AbortController();
    fetchIncidentTimeline(WORKSPACE, selectedId, controller.signal)
      .then(setEvents)
      .catch((caught: unknown) => {
        if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : "Unable to load timeline");
      });
    return () => controller.abort();
  }, [demoMode, selectedId]);

  useEffect(() => {
    const playbook = playbooks.find((item) => item.id === selectedPlaybookId);
    if (!playbook) {
      setPlaybookVersion(null);
      return;
    }
    if (demoMode) {
      setPlaybookVersion({
        ...DEMO_PLAYBOOK_VERSION,
        playbook_id: playbook.id,
        number: playbook.latest_version,
      });
      return;
    }
    const controller = new AbortController();
    fetchPlaybookVersion(
      WORKSPACE,
      playbook.id,
      playbook.latest_version,
      controller.signal,
    )
      .then(setPlaybookVersion)
      .catch((caught: unknown) => {
        if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : "Unable to load playbook revision");
      });
    return () => controller.abort();
  }, [demoMode, playbooks, selectedPlaybookId]);

  const selected = incidents.find((incident) => incident.id === selectedId) ?? null;
  const selectedPlaybook = playbooks.find((playbook) => playbook.id === selectedPlaybookId) ?? null;
  const selectedWorkflow = workflows.find((workflow) => workflow.id === selectedWorkflowId) ?? null;
  const approvals = incidents.filter((incident) => incident.status === "awaiting_approval");
  const openIncidents = incidents.filter((incident) => !["resolved", "closed"].includes(incident.status));
  const filtered = useMemo(() => incidents.filter((incident) => {
    const matchesText = `${incident.title} ${incident.id}`.toLowerCase().includes(query.toLowerCase());
    return matchesText && (severityFilter === "all" || incident.severity === severityFilter);
  }), [incidents, query, severityFilter]);

  const runtimeState = readiness?.status === "ready" ? "Operational" : unavailable ? "Unavailable" : "Checking";

  function chooseIncident(incident: Incident) {
    setSelectedId(incident.id);
    if (view !== "overview") setView("incidents");
  }

  async function handleCreate(input: CreateIncidentInput) {
    setMutating(true);
    setError(null);
    try {
      const created = demoMode
        ? {
            id: `${Math.random().toString(16).slice(2, 10)}-demo-4000-8000-000000000000`,
            workspace_id: WORKSPACE.workspaceId,
            ...input,
            status: "new" as const,
            version: 1,
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
            resolved_at: null,
            closed_at: null,
          }
        : await createIncident(WORKSPACE, input);
      setIncidents((current) => [created, ...current]);
      setSelectedId(created.id);
      setCreateOpen(false);
      setView("incidents");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to create incident");
    } finally {
      setMutating(false);
    }
  }

  async function handleAdvance(incident: Incident) {
    const target = NEXT_STATUS[incident.status];
    if (!target) return;
    setMutating(true);
    setError(null);
    try {
      const changed = demoMode
        ? { ...incident, status: target, version: incident.version + 1, updated_at: new Date().toISOString() }
        : await transitionIncident(
            WORKSPACE,
            incident,
            target,
            incident.status === "awaiting_approval" ? "Approved in SentinelFlow operations console" : `Advanced to ${target} by operator`,
          );
      setIncidents((current) => current.map((item) => item.id === changed.id ? changed : item));
      setEvents((current) => [{
        id: `event-${Date.now()}`,
        incident_id: incident.id,
        sequence: changed.version,
        event_type: "status_changed",
        actor_id: WORKSPACE.actorId,
        data: { from_status: incident.status, to_status: target, reason: "Operator action from control console" },
        occurred_at: changed.updated_at,
      }, ...current]);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to update incident");
    } finally {
      setMutating(false);
    }
  }

  async function handlePublishPlaybook(playbook: Playbook) {
    setMutating(true);
    setError(null);
    try {
      const published = demoMode
        ? {
            ...playbook,
            status: "active" as const,
            active_version: playbook.latest_version,
            version: playbook.version + 1,
            updated_at: new Date().toISOString(),
          }
        : await publishPlaybook(WORKSPACE, playbook);
      setPlaybooks((current) => current.map((item) => item.id === published.id ? published : item));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to publish playbook");
    } finally {
      setMutating(false);
    }
  }

  async function handleStartWorkflow(workflow: Workflow) {
    setMutating(true);
    setError(null);
    try {
      const started = demoMode
        ? {
            ...workflow,
            status: (workflow.steps[0]?.kind === "approval" ? "awaiting_approval" : "running") as WorkflowStatus,
            version: workflow.version + 1,
            started_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
            steps: workflow.steps.map((step, index) => index === 0 ? {
              ...step,
              status: step.kind === "approval" ? "waiting_approval" as const : "running" as const,
              attempt: 1,
              started_at: new Date().toISOString(),
            } : step),
          }
        : await startWorkflow(WORKSPACE, workflow);
      setWorkflows((current) => current.map((item) => item.id === started.id ? started : item));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to start workflow");
    } finally {
      setMutating(false);
    }
  }

  async function handleApproveWorkflow(workflow: Workflow) {
    const approval = workflow.steps.find((step) => step.status === "waiting_approval");
    if (!approval) return;
    setMutating(true);
    setError(null);
    try {
      const approved = demoMode
        ? {
            ...workflow,
            status: "running" as const,
            version: workflow.version + 1,
            updated_at: new Date().toISOString(),
            steps: workflow.steps.map((step, index, steps) => {
              if (step.id === approval.id) {
                return { ...step, status: "succeeded" as const, finished_at: new Date().toISOString() };
              }
              if (steps[index - 1]?.id === approval.id) {
                return { ...step, status: "running" as const, attempt: 1, started_at: new Date().toISOString() };
              }
              return step;
            }),
          }
        : await approveWorkflowStep(WORKSPACE, workflow, approval.step_key);
      setWorkflows((current) => current.map((item) => item.id === approved.id ? approved : item));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to approve workflow step");
    } finally {
      setMutating(false);
    }
  }

  const navigation: { id: View; label: string; icon: IconName; count?: number }[] = [
    { id: "overview", label: "Overview", icon: "grid" },
    { id: "incidents", label: "Incidents", icon: "alert", count: openIncidents.length },
    { id: "approvals", label: "Approvals", icon: "approval", count: approvals.length },
    { id: "playbooks", label: "Playbooks", icon: "spark", count: playbooks.filter((playbook) => playbook.status === "draft").length },
    { id: "workflows", label: "Workflows", icon: "activity", count: workflows.filter((workflow) => !["succeeded", "failed", "cancelled"].includes(workflow.status)).length },
    { id: "integrations", label: "Integrations", icon: "integration" },
  ];

  return (
    <div className="app-shell">
      <aside className={sidebarOpen ? "sidebar sidebar-open" : "sidebar"}>
        <a className="brand" href={demoMode ? "?demo=1" : "/"} aria-label="SentinelFlow home">
          <span className="brand-mark"><Icon name="shield" size={19} /></span>
          <span>Sentinel<span>Flow</span></span>
        </a>
        <p className="nav-label">Workspace</p>
        <nav aria-label="Main navigation">
          {navigation.map((item) => (
            <button
              className={view === item.id ? "active" : ""}
              key={item.id}
              type="button"
              onClick={() => { setView(item.id); setSidebarOpen(false); }}
            >
              <Icon name={item.icon} />
              <span>{item.label}</span>
              {item.count !== undefined && item.count > 0 && <b>{item.count}</b>}
            </button>
          ))}
        </nav>
        <div className="sidebar-lower">
          <div className={`runtime-state runtime-${runtimeState.toLowerCase()}`} role="status">
            <span className="runtime-dot" />
            <div>
              <strong>{runtimeState}</strong>
              <small>{demoMode ? "Demo workspace" : readiness ? `${Object.keys(readiness.checks).length} services healthy` : "Connecting services"}</small>
            </div>
          </div>
          <div className="operator">
            <span>MP</span>
            <div><strong>Mina Park</strong><small>Security operator</small></div>
          </div>
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <button className="mobile-menu icon-button" type="button" aria-label="Open navigation" onClick={() => setSidebarOpen((current) => !current)}><Icon name="menu" /></button>
          <div className="workspace-switcher">
            <span>Production workspace</span>
            <Icon name="chevron" size={14} />
          </div>
          <div className="topbar-actions">
            <label className="global-search">
              <span className="sr-only">Search incidents</span>
              <Icon name="search" size={16} />
              <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search incidents" />
              <kbd>⌘ K</kbd>
            </label>
            <span className="live-chip"><i /> {demoMode ? "Demo" : "Live"}</span>
            <button className="avatar-button" type="button" aria-label="Operator profile">MP</button>
          </div>
        </header>

        <div className="page">
          {error && (
            <div className="error-banner" role="alert">
              <Icon name="alert" size={17} />
              <span>{error}</span>
              <button type="button" onClick={() => setError(null)} aria-label="Dismiss error"><Icon name="x" size={15} /></button>
            </div>
          )}

          {view === "overview" && (
            <>
              <div className="page-heading">
                <div>
                  <p className="eyebrow">COMMAND CENTER · JUL 28, 2026</p>
                  <h1>Operations overview</h1>
                  <p>Monitor risk, control response boundaries, and keep every action auditable.</p>
                </div>
                <button className="button primary" type="button" onClick={() => setCreateOpen(true)}><Icon name="plus" size={17} />New incident</button>
              </div>

              <section className="metrics" aria-label="Security operations metrics">
                <article className="metric-card metric-critical">
                  <div><span>Open incidents</span><Icon name="alert" /></div>
                  <strong>{String(openIncidents.length).padStart(2, "0")}</strong>
                  <p><b>↑ 2</b> in the last 24 hours</p>
                  <div className="mini-bars">{[31, 42, 36, 56, 48, 70, 62, 85, 74, 91].map((height, index) => <i key={index} style={{ height: `${height}%` }} />)}</div>
                </article>
                <article className="metric-card metric-approval">
                  <div><span>Awaiting approval</span><Icon name="approval" /></div>
                  <strong>{String(approvals.length).padStart(2, "0")}</strong>
                  <p><b>{approvals.length ? "Action required" : "Queue clear"}</b> · policy protected</p>
                  <span className="metric-orbit"><i /></span>
                </article>
                <article className="metric-card">
                  <div><span>Mean time to detect</span><Icon name="clock" /></div>
                  <strong>2m <small>14s</small></strong>
                  <p><em>↓ 18%</em> from last week</p>
                  <svg className="sparkline" viewBox="0 0 180 44" preserveAspectRatio="none"><path d="M0 35 C18 32, 24 17, 42 22 S72 39, 91 24 S115 10, 132 18 S158 24, 180 7" /><path className="spark-fill" d="M0 35 C18 32,24 17,42 22 S72 39,91 24 S115 10,132 18 S158 24,180 7 V44 H0Z" /></svg>
                </article>
                <article className="metric-card">
                  <div><span>Response coverage</span><Icon name="shield" /></div>
                  <strong>94<small>%</small></strong>
                  <p><em>↑ 4.2%</em> automation ready</p>
                  <div className="coverage-track"><i /></div>
                </article>
              </section>

              <section className="overview-grid">
                <article className="panel queue-panel">
                  <div className="panel-heading">
                    <div><h2>Active incident queue</h2><p>Prioritized by severity and response SLA</p></div>
                    <button className="text-button" type="button" onClick={() => setView("incidents")}>View all <Icon name="arrow" size={14} /></button>
                  </div>
                  {loading ? <div className="loading-rows"><i /><i /><i /><i /></div> : <IncidentTable incidents={filtered.slice(0, 5)} selectedId={selectedId} onSelect={chooseIncident} />}
                </article>

                <article className="panel posture-panel">
                  <div className="panel-heading">
                    <div><h2>Response posture</h2><p>Live control-plane confidence</p></div>
                    <span className="healthy-chip"><i />Healthy</span>
                  </div>
                  <div className="posture-score">
                    <div className="score-ring"><strong>92</strong><small>/100</small></div>
                    <div><strong>Controls are ready</strong><p>5 of 6 service boundaries are operating within policy.</p></div>
                  </div>
                  <div className="control-list">
                    {[
                      ["Detection coverage", "98%"],
                      ["Approval enforcement", "100%"],
                      ["Adapter availability", "96%"],
                    ].map(([label, value]) => <div key={label}><span>{label}</span><i><b style={{ width: value }} /></i><strong>{value}</strong></div>)}
                  </div>
                  <button className="posture-link" type="button" onClick={() => setView("integrations")}>Inspect service boundaries <Icon name="chevron" size={14} /></button>
                </article>

                <article className="panel response-panel">
                  <div className="panel-heading">
                    <div><h2>Live response</h2><p>Selected incident and immutable timeline</p></div>
                    <span className="append-chip">Append-only</span>
                  </div>
                  <Timeline incident={selected} events={events} busy={mutating} onAdvance={handleAdvance} />
                </article>

                <article className="panel approval-panel">
                  <div className="panel-heading">
                    <div><h2>Approval queue</h2><p>High-risk actions waiting for a human</p></div>
                    <span className="count-chip">{approvals.length}</span>
                  </div>
                  {approvals.length ? approvals.slice(0, 2).map((incident) => (
                    <div className="approval-item" key={incident.id}>
                      <div className="approval-symbol"><Icon name="spark" size={17} /></div>
                      <div>
                        <strong>Isolate endpoint</strong>
                        <p>{incident.title}</p>
                        <small><Icon name="clock" size={12} />Expires in 18m · Patchtower</small>
                      </div>
                      <button type="button" onClick={() => { setSelectedId(incident.id); setView("approvals"); }}><Icon name="chevron" size={16} /></button>
                    </div>
                  )) : <EmptyState title="Approval queue clear" copy="No high-risk response is waiting for operator review." />}
                  <div className="policy-note"><Icon name="shield" size={15} /><span>AI cannot execute high-risk actions without approval.</span></div>
                </article>
              </section>
            </>
          )}

          {view === "incidents" && (
            <>
              <div className="page-heading compact-heading">
                <div><p className="eyebrow">INCIDENT MANAGEMENT</p><h1>Incident queue</h1><p>Investigate, prioritize, and advance cases through the controlled lifecycle.</p></div>
                <button className="button primary" type="button" onClick={() => setCreateOpen(true)}><Icon name="plus" size={17} />New incident</button>
              </div>
              <div className="filterbar">
                <div className="filter-search"><Icon name="search" size={16} /><input aria-label="Filter incidents" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Filter by title or incident ID" /></div>
                <div className="filter-pills">
                  {(["all", "critical", "high", "medium", "low"] as const).map((value) => <button className={severityFilter === value ? "active" : ""} type="button" key={value} onClick={() => setSeverityFilter(value)}>{value}</button>)}
                </div>
              </div>
              <section className="detail-layout">
                <article className="panel full-table">
                  <div className="panel-heading"><div><h2>All incidents</h2><p>{filtered.length} cases in the current workspace</p></div><span className="append-chip">Workspace isolated</span></div>
                  <IncidentTable incidents={filtered} selectedId={selectedId} onSelect={chooseIncident} />
                </article>
                <article className="panel inspector">
                  <div className="panel-heading"><div><h2>Incident inspector</h2><p>Lifecycle, evidence, and operator action</p></div></div>
                  <Timeline incident={selected} events={events} busy={mutating} onAdvance={handleAdvance} />
                </article>
              </section>
            </>
          )}

          {view === "approvals" && (
            <>
              <div className="page-heading compact-heading">
                <div><p className="eyebrow">HUMAN-IN-THE-LOOP CONTROL</p><h1>Approval queue</h1><p>Review consequential response actions before they cross a protected boundary.</p></div>
              </div>
              <section className="approval-workspace">
                <div className="approval-callout"><Icon name="shield" size={22} /><div><strong>Policy enforcement active</strong><p>Critical response actions require an authenticated human decision and a durable audit event.</p></div><span>{approvals.length} pending</span></div>
                {approvals.length ? approvals.map((incident) => (
                  <article className="approval-card" key={incident.id}>
                    <div className="approval-card-main">
                      <div className="approval-symbol large"><Icon name="alert" /></div>
                      <div>
                        <span className="incident-id">{shortId(incident.id)} · PATCHTOWER</span>
                        <h2>Isolate affected endpoint and revoke active sessions</h2>
                        <p>{incident.description}</p>
                        <div className="risk-row"><SeverityBadge severity={incident.severity} /><span><Icon name="clock" size={13} />Requested {formatRelative(incident.updated_at)}</span><span><Icon name="spark" size={13} />AI confidence 94%</span></div>
                      </div>
                    </div>
                    <div className="approval-card-actions">
                      <button className="button secondary" type="button" onClick={() => { setSelectedId(incident.id); setView("incidents"); }}>Review evidence</button>
                      <button className="button primary" type="button" disabled={mutating} onClick={() => handleAdvance(incident)}><Icon name="check" size={16} />Approve action</button>
                    </div>
                  </article>
                )) : <article className="panel"><EmptyState title="Approval queue clear" copy="All proposed high-risk actions have been reviewed." /></article>}
              </section>
            </>
          )}

          {view === "playbooks" && (
            <>
              <div className="page-heading compact-heading">
                <div><p className="eyebrow">VERSIONED RESPONSE CONTROL</p><h1>Response playbooks</h1><p>Review immutable definitions before they become executable workflow policy.</p></div>
                <span className="playbook-security-chip"><Icon name="shield" size={15} />Guardrails enforced</span>
              </div>
              <div className="playbook-summary">
                <div><strong>{playbooks.length}</strong><span>Versioned playbooks</span></div>
                <div><strong>{playbooks.filter((playbook) => playbook.status === "active").length}</strong><span>Active definitions</span></div>
                <div><strong>{playbooks.reduce((total, playbook) => total + playbook.latest_version, 0)}</strong><span>Immutable revisions</span></div>
                <div><strong>SHA-256</strong><span>Content attestation</span></div>
              </div>
              <section className="playbook-layout">
                <article className="panel playbook-list-panel">
                  <div className="panel-heading">
                    <div><h2>Playbook library</h2><p>Workspace-scoped definitions and active revision pointers</p></div>
                    <span className="append-chip">Immutable versions</span>
                  </div>
                  <div className="playbook-list">
                    {playbooks.length ? playbooks.map((playbook) => (
                      <button
                        className={selectedPlaybookId === playbook.id ? "playbook-row selected" : "playbook-row"}
                        key={playbook.id}
                        type="button"
                        onClick={() => setSelectedPlaybookId(playbook.id)}
                      >
                        <span className="playbook-row-icon"><Icon name="spark" size={16} /></span>
                        <span className="playbook-row-copy">
                          <strong>{playbook.name}</strong>
                          <small>{playbook.description}</small>
                          <span><b className={`playbook-status playbook-${playbook.status}`}>{playbook.status}</b>Revision {playbook.latest_version} · updated {formatRelative(playbook.updated_at)}</span>
                        </span>
                        <Icon name="chevron" size={15} />
                      </button>
                    )) : <EmptyState title="No playbooks yet" copy="Create the first versioned response definition through the Playbook API." />}
                  </div>
                </article>
                <article className="panel playbook-inspector">
                  <div className="panel-heading">
                    <div><h2>Definition inspector</h2><p>Typed steps, risk gates, and recovery guarantees</p></div>
                    {selectedPlaybook && <span className="version-chip">REV {selectedPlaybook.latest_version}</span>}
                  </div>
                  {selectedPlaybook && playbookVersion ? (
                    <div className="playbook-definition">
                      <div className="definition-heading">
                        <div><span className="incident-id">{selectedPlaybook.status.toUpperCase()} · {playbookVersion.steps.length} STEPS</span><h3>{selectedPlaybook.name}</h3></div>
                        <span className="hash-badge" title={playbookVersion.definition_hash}><Icon name="shield" size={13} />{playbookVersion.definition_hash.slice(0, 10)}</span>
                      </div>
                      <p>{selectedPlaybook.description}</p>
                      <div className="step-chain">
                        {playbookVersion.steps.map((step, index) => (
                          <article className={`playbook-step step-${step.kind}`} key={step.key}>
                            <div className="step-index">{index + 1}</div>
                            <div className="step-copy">
                              <span>{step.kind}</span>
                              <strong>{step.name}</strong>
                              <small>{step.adapter ? `${step.adapter} · ${step.operation}` : "Human decision boundary"}</small>
                            </div>
                            <div className="step-controls">
                              <SeverityBadge severity={step.risk} />
                              {step.rollback && <span className="rollback-chip"><Icon name="activity" size={11} />Rollback</span>}
                            </div>
                          </article>
                        ))}
                      </div>
                      <div className="definition-guards">
                        <span><Icon name="approval" size={14} /><b>Approval gate</b> before critical action</span>
                        <span><Icon name="activity" size={14} /><b>Compensation</b> explicitly defined</span>
                        <span><Icon name="shield" size={14} /><b>Content hash</b> verified on load</span>
                      </div>
                      <div className="definition-footer">
                        <div><small>Created by</small><strong>{playbookVersion.created_by}</strong></div>
                        <div><small>Active revision</small><strong>{selectedPlaybook.active_version ? `Revision ${selectedPlaybook.active_version}` : "Not published"}</strong></div>
                        {selectedPlaybook.active_version !== selectedPlaybook.latest_version ? (
                          <button className="button primary" type="button" disabled={mutating || selectedPlaybook.status === "archived"} onClick={() => handlePublishPlaybook(selectedPlaybook)}>
                            <Icon name="check" size={15} />{mutating ? "Publishing…" : "Publish latest"}
                          </button>
                        ) : <span className="published-label"><Icon name="check" size={13} />Published</span>}
                      </div>
                    </div>
                  ) : <EmptyState title="Select a playbook" copy="Choose a response definition to inspect its latest immutable revision." />}
                </article>
              </section>
            </>
          )}

          {view === "workflows" && (
            <>
              <div className="page-heading compact-heading">
                <div><p className="eyebrow">AUDITABLE EXECUTION ENGINE</p><h1>Workflow runs</h1><p>Operate response policy with explicit state, bounded retries, and reversible actions.</p></div>
                <span className="workflow-engine-chip"><span className="runtime-dot" />Engine policy active</span>
              </div>
              <div className="workflow-summary">
                <div><strong>{workflows.length}</strong><span>Total runs</span></div>
                <div><strong>{workflows.filter((workflow) => workflow.status === "running").length}</strong><span>Executing</span></div>
                <div><strong>{workflows.filter((workflow) => workflow.status === "awaiting_approval").length}</strong><span>Awaiting approval</span></div>
                <div><strong>{workflows.filter((workflow) => workflow.status === "compensating").length}</strong><span>Compensating</span></div>
              </div>
              <section className="workflow-layout">
                <article className="panel workflow-list-panel">
                  <div className="panel-heading">
                    <div><h2>Execution ledger</h2><p>Workspace-isolated workflow aggregates</p></div>
                    <span className="append-chip">Version locked</span>
                  </div>
                  <div className="workflow-list">
                    {workflows.length ? workflows.map((workflow) => {
                      const incident = incidents.find((item) => item.id === workflow.incident_id);
                      const playbook = playbooks.find((item) => item.id === workflow.playbook_id);
                      const completed = workflow.steps.filter((step) => ["succeeded", "skipped", "compensated"].includes(step.status)).length;
                      const progress = workflow.steps.length ? Math.round((completed / workflow.steps.length) * 100) : workflow.status === "succeeded" ? 100 : 48;
                      return (
                        <button
                          className={selectedWorkflowId === workflow.id ? "workflow-row selected" : "workflow-row"}
                          key={workflow.id}
                          type="button"
                          onClick={() => setSelectedWorkflowId(workflow.id)}
                        >
                          <span className={`workflow-state-indicator workflow-${workflow.status}`}><Icon name={workflow.status === "awaiting_approval" ? "approval" : workflow.status === "succeeded" ? "check" : "activity"} size={15} /></span>
                          <span className="workflow-row-copy">
                            <span><b>{shortWorkflowId(workflow.id)}</b><i className={`workflow-status workflow-${workflow.status}`}>{WORKFLOW_STATUS_LABELS[workflow.status]}</i></span>
                            <strong>{playbook?.name ?? `Playbook revision ${workflow.playbook_version}`}</strong>
                            <small>{incident?.title ?? shortId(workflow.incident_id)}</small>
                            <span className="workflow-progress"><i style={{ width: `${progress}%` }} /><b>{progress}%</b></span>
                          </span>
                          <Icon name="chevron" size={15} />
                        </button>
                      );
                    }) : <EmptyState title="No workflow runs" copy="Create a run from a published playbook revision through the Workflow API." />}
                  </div>
                </article>
                <article className="panel workflow-inspector">
                  <div className="panel-heading">
                    <div><h2>Run inspector</h2><p>Current state, step attempts, and recovery path</p></div>
                    {selectedWorkflow && <span className={`workflow-status workflow-${selectedWorkflow.status}`}>{WORKFLOW_STATUS_LABELS[selectedWorkflow.status]}</span>}
                  </div>
                  {selectedWorkflow ? (
                    <div className="workflow-detail">
                      <div className="workflow-detail-heading">
                        <div>
                          <span className="incident-id">{shortWorkflowId(selectedWorkflow.id)} · REVISION {selectedWorkflow.playbook_version}</span>
                          <h3>{playbooks.find((item) => item.id === selectedWorkflow.playbook_id)?.name ?? "Response workflow"}</h3>
                          <p>{incidents.find((item) => item.id === selectedWorkflow.incident_id)?.title ?? shortId(selectedWorkflow.incident_id)}</p>
                        </div>
                        <span className="hash-badge" title={selectedWorkflow.definition_hash}><Icon name="shield" size={13} />{selectedWorkflow.definition_hash.slice(0, 10)}</span>
                      </div>
                      <div className="workflow-assurance">
                        <span><small>Optimistic version</small><strong>v{selectedWorkflow.version}</strong></span>
                        <span><small>Started</small><strong>{selectedWorkflow.started_at ? formatRelative(selectedWorkflow.started_at) : "Not started"}</strong></span>
                        <span><small>Retry policy</small><strong>Max 3 attempts</strong></span>
                        <span><small>Audit events</small><strong>Append only</strong></span>
                      </div>
                      {selectedWorkflow.steps.length ? (
                        <div className="workflow-step-list">
                          {selectedWorkflow.steps.map((step, index) => (
                            <article className={`workflow-step workflow-step-${step.status}`} key={step.id}>
                              <div className="workflow-step-marker">
                                <span>{["succeeded", "compensated"].includes(step.status) ? <Icon name="check" size={13} /> : index + 1}</span>
                                {index < selectedWorkflow.steps.length - 1 && <i />}
                              </div>
                              <div className="workflow-step-copy">
                                <span>{step.kind} · {step.adapter ?? "operator"}</span>
                                <strong>{step.name}</strong>
                                <small>{step.operation ?? "Authenticated human decision"} · timeout {step.timeout_seconds}s</small>
                              </div>
                              <div className="workflow-step-meta">
                                <span className={`step-run-state state-${step.status}`}>{WORKFLOW_STEP_STATUS_LABELS[step.status]}</span>
                                <small>Attempt {step.attempt}/{step.max_attempts}</small>
                                {step.rollback_operation && <small className="recovery-ready"><Icon name="activity" size={10} />Recovery ready</small>}
                              </div>
                            </article>
                          ))}
                        </div>
                      ) : <div className="workflow-empty-steps"><Icon name="activity" size={21} /><span>Step snapshot retained by the execution ledger</span></div>}
                      <div className="workflow-detail-footer">
                        <span><Icon name="shield" size={14} />Pinned to immutable definition <b>{selectedWorkflow.definition_hash.slice(0, 12)}</b></span>
                        {selectedWorkflow.status === "pending" && (
                          <button className="button primary" type="button" disabled={mutating} onClick={() => handleStartWorkflow(selectedWorkflow)}>
                            <Icon name="activity" size={15} />{mutating ? "Starting…" : "Start workflow"}
                          </button>
                        )}
                        {selectedWorkflow.status === "awaiting_approval" && (
                          <button className="button primary" type="button" disabled={mutating} onClick={() => handleApproveWorkflow(selectedWorkflow)}>
                            <Icon name="check" size={15} />{mutating ? "Approving…" : "Approve current step"}
                          </button>
                        )}
                      </div>
                    </div>
                  ) : <EmptyState title="Select a workflow" copy="Choose an execution run to inspect its current durable state." />}
                </article>
              </section>
            </>
          )}

          {view === "integrations" && (
            <>
              <div className="page-heading compact-heading">
                <div><p className="eyebrow">SERVICE BOUNDARIES</p><h1>Integrations</h1><p>Observe every security adapter without exposing credentials or vendor internals.</p></div>
              </div>
              <div className="integration-summary">
                <div><span className="runtime-dot" /><strong>4 connected</strong><small>All required services are healthy</small></div>
                <div><strong>54 ms</strong><small>Median adapter latency</small></div>
                <div><strong>0</strong><small>Open circuit breakers</small></div>
              </div>
              <section className="integration-grid">
                {INTEGRATIONS.map((integration) => (
                  <article className="integration-card" key={integration.name}>
                    <div className={`integration-logo logo-${integration.tone}`}>{integration.name.slice(0, 2).toUpperCase()}</div>
                    <div className="integration-card-heading"><div><h2>{integration.name}</h2><p>{integration.detail}</p></div><span className={integration.state === "Connected" || integration.state === "Ready" ? "connected" : ""}><i />{integration.state}</span></div>
                    <div className="adapter-stats"><div><span>Latency</span><strong>{integration.latency}</strong></div><div><span>Policy</span><strong>Enforced</strong></div><div><span>Credential</span><strong>Referenced</strong></div></div>
                    <button type="button">View adapter policy <Icon name="chevron" size={14} /></button>
                  </article>
                ))}
              </section>
            </>
          )}
        </div>
      </main>

      {createOpen && <CreateIncidentModal busy={mutating} error={error} onClose={() => { setCreateOpen(false); setError(null); }} onCreate={handleCreate} />}
      {sidebarOpen && <button className="sidebar-scrim" type="button" aria-label="Close navigation" onClick={() => setSidebarOpen(false)} />}
    </div>
  );
}
