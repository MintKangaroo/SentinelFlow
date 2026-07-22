export type Readiness = {
  status: "ready" | "not_ready";
  checks: Record<string, "ok" | "error">;
};

export async function fetchReadiness(signal?: AbortSignal): Promise<Readiness> {
  const response = await fetch("/api/v1/health/ready", {
    headers: { Accept: "application/json" },
    signal,
  });
  if (!response.ok) {
    throw new Error("The control plane is not ready");
  }
  return (await response.json()) as Readiness;
}
