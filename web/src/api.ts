export type Readiness = {
  status: "ready" | "not_ready";
  checks: Record<string, "ok" | "error">;
};

export type IncidentStatus =
  | "new"
  | "triaging"
  | "investigating"
  | "awaiting_approval"
  | "responding"
  | "validating"
  | "resolved"
  | "closed"
  | "reopened";

export type IncidentSeverity = "low" | "medium" | "high" | "critical";

export type Incident = {
  id: string;
  workspace_id: string;
  title: string;
  description: string;
  severity: IncidentSeverity;
  status: IncidentStatus;
  version: number;
  created_at: string;
  updated_at: string;
  resolved_at: string | null;
  closed_at: string | null;
};

export type IncidentEvent = {
  id: string;
  incident_id: string;
  sequence: number;
  event_type: "incident_created" | "status_changed" | "note_added";
  actor_id: string;
  data: Record<string, string | number | boolean | null>;
  occurred_at: string;
};

export type ApiContext = {
  workspaceId: string;
  actorId: string;
};

export type CreateIncidentInput = {
  title: string;
  description: string;
  severity: IncidentSeverity;
};

export type PlaybookStatus = "draft" | "active" | "archived";
export type PlaybookStepKind =
  | "enrichment"
  | "approval"
  | "action"
  | "validation"
  | "notification";

export type Playbook = {
  id: string;
  workspace_id: string;
  name: string;
  description: string;
  status: PlaybookStatus;
  latest_version: number;
  active_version: number | null;
  version: number;
  created_at: string;
  updated_at: string;
  archived_at: string | null;
};

export type PlaybookStep = {
  key: string;
  name: string;
  kind: PlaybookStepKind;
  risk: IncidentSeverity;
  adapter: string | null;
  operation: string | null;
  parameters: Record<string, unknown>;
  timeout_seconds: number;
  continue_on_failure: boolean;
  condition: {
    field: string;
    operator: "equals" | "not_equals" | "contains" | "exists" | "in";
    value: unknown;
  } | null;
  rollback: {
    strategy: "compensate" | "restore";
    operation: string;
    parameters: Record<string, unknown>;
    timeout_seconds: number;
  } | null;
};

export type PlaybookVersion = {
  id: string;
  workspace_id: string;
  playbook_id: string;
  number: number;
  steps: PlaybookStep[];
  definition_hash: string;
  created_by: string;
  created_at: string;
};

export type WorkflowStatus =
  | "pending"
  | "running"
  | "awaiting_approval"
  | "compensating"
  | "succeeded"
  | "failed"
  | "cancelled";

export type WorkflowStepStatus =
  | "pending"
  | "running"
  | "waiting_approval"
  | "succeeded"
  | "failed"
  | "skipped"
  | "compensating"
  | "compensated";

export type WorkflowStep = {
  id: string;
  position: number;
  step_key: string;
  name: string;
  kind: PlaybookStepKind;
  risk: IncidentSeverity;
  adapter: string | null;
  operation: string | null;
  timeout_seconds: number;
  max_attempts: number;
  rollback_strategy: "compensate" | "restore" | null;
  rollback_operation: string | null;
  parameters: Record<string, unknown>;
  continue_on_failure: boolean;
  condition: Record<string, unknown> | null;
  rollback_parameters: Record<string, unknown>;
  rollback_timeout_seconds: number;
  status: WorkflowStepStatus;
  attempt: number;
  output: Record<string, unknown>;
  last_error_code: string | null;
  started_at: string | null;
  finished_at: string | null;
};

export type Workflow = {
  id: string;
  workspace_id: string;
  incident_id: string;
  playbook_id: string;
  playbook_version_id: string;
  playbook_version: number;
  definition_hash: string;
  status: WorkflowStatus;
  version: number;
  created_by: string;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  finished_at: string | null;
  cancel_requested: boolean;
  steps: WorkflowStep[];
};

function requestHeaders(context: ApiContext, write = false): HeadersInit {
  const headers: Record<string, string> = {
    Accept: "application/json",
    "X-Workspace-ID": context.workspaceId,
  };
  if (write) {
    headers["Content-Type"] = "application/json";
    headers["X-Actor-ID"] = context.actorId;
    headers["Idempotency-Key"] = createIdempotencyKey();
  }
  return headers;
}

function createIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `web-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

async function parseResponse<T>(response: Response): Promise<T> {
  if (response.ok) {
    return (await response.json()) as T;
  }

  let message = `Request failed with status ${response.status}`;
  try {
    const body = (await response.json()) as { error?: { message?: string }; detail?: string };
    message = body.error?.message ?? body.detail ?? message;
  } catch {
    // Keep the stable status-only fallback when the dependency returns a non-JSON body.
  }
  throw new Error(message);
}

export async function fetchReadiness(signal?: AbortSignal): Promise<Readiness> {
  const response = await fetch("/api/v1/health/ready", {
    headers: { Accept: "application/json" },
    signal,
  });
  return parseResponse<Readiness>(response);
}

export async function fetchIncidents(
  context: ApiContext,
  signal?: AbortSignal,
): Promise<Incident[]> {
  const response = await fetch("/api/v1/incidents?limit=200", {
    headers: requestHeaders(context),
    signal,
  });
  return parseResponse<Incident[]>(response);
}

export async function fetchIncidentTimeline(
  context: ApiContext,
  incidentId: string,
  signal?: AbortSignal,
): Promise<IncidentEvent[]> {
  const response = await fetch(`/api/v1/incidents/${incidentId}/timeline?limit=100`, {
    headers: requestHeaders(context),
    signal,
  });
  return parseResponse<IncidentEvent[]>(response);
}

export async function createIncident(
  context: ApiContext,
  input: CreateIncidentInput,
): Promise<Incident> {
  const response = await fetch("/api/v1/incidents", {
    method: "POST",
    headers: requestHeaders(context, true),
    body: JSON.stringify(input),
  });
  return parseResponse<Incident>(response);
}

export async function transitionIncident(
  context: ApiContext,
  incident: Incident,
  targetStatus: IncidentStatus,
  reason: string,
): Promise<Incident> {
  const response = await fetch(`/api/v1/incidents/${incident.id}/transitions`, {
    method: "POST",
    headers: requestHeaders(context, true),
    body: JSON.stringify({
      target_status: targetStatus,
      reason,
      expected_version: incident.version,
    }),
  });
  return parseResponse<Incident>(response);
}

export async function fetchPlaybooks(
  context: ApiContext,
  signal?: AbortSignal,
): Promise<Playbook[]> {
  const response = await fetch("/api/v1/playbooks?limit=200", {
    headers: requestHeaders(context),
    signal,
  });
  return parseResponse<Playbook[]>(response);
}

export async function fetchPlaybookVersion(
  context: ApiContext,
  playbookId: string,
  version: number,
  signal?: AbortSignal,
): Promise<PlaybookVersion> {
  const response = await fetch(`/api/v1/playbooks/${playbookId}/versions/${version}`, {
    headers: requestHeaders(context),
    signal,
  });
  return parseResponse<PlaybookVersion>(response);
}

export async function publishPlaybook(
  context: ApiContext,
  playbook: Playbook,
): Promise<Playbook> {
  const response = await fetch(
    `/api/v1/playbooks/${playbook.id}/versions/${playbook.latest_version}/publish`,
    {
      method: "POST",
      headers: requestHeaders(context, true),
      body: JSON.stringify({ expected_version: playbook.version }),
    },
  );
  return parseResponse<Playbook>(response);
}

export async function fetchWorkflows(
  context: ApiContext,
  signal?: AbortSignal,
): Promise<Workflow[]> {
  const response = await fetch("/api/v1/workflows?limit=200", {
    headers: requestHeaders(context),
    signal,
  });
  return parseResponse<Workflow[]>(response);
}

export async function startWorkflow(
  context: ApiContext,
  workflow: Workflow,
): Promise<Workflow> {
  const response = await fetch(`/api/v1/workflows/${workflow.id}/start`, {
    method: "POST",
    headers: requestHeaders(context, true),
    body: JSON.stringify({ expected_version: workflow.version }),
  });
  return parseResponse<Workflow>(response);
}

export async function approveWorkflowStep(
  context: ApiContext,
  workflow: Workflow,
  stepKey: string,
): Promise<Workflow> {
  const response = await fetch(
    `/api/v1/workflows/${workflow.id}/steps/${stepKey}/approval`,
    {
      method: "POST",
      headers: requestHeaders(context, true),
      body: JSON.stringify({ expected_version: workflow.version, approved: true }),
    },
  );
  return parseResponse<Workflow>(response);
}
