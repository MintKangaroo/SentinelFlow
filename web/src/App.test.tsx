import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";

describe("App", () => {
  afterEach(() => {
    cleanup();
    window.history.replaceState({}, "", "/");
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("shows live readiness and the empty incident workspace", async () => {
    vi.stubGlobal("fetch", vi.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/health/ready")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ status: "ready", checks: { database: "ok", redis: "ok" } }),
        });
      }
      return Promise.resolve({ ok: true, json: async () => [] });
    }));

    render(<App />);

    expect(screen.getByRole("heading", { name: "Operations overview" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Operational"));
    expect(screen.getByRole("status")).toHaveTextContent("2 services healthy");
    await waitFor(() => expect(screen.getByText("No incidents in this view")).toBeInTheDocument());
  });

  it("shows an unavailable state when the control plane cannot be reached", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));

    render(<App />);

    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Unavailable"));
    expect(screen.getByRole("alert")).toHaveTextContent("offline");
  });

  it("navigates the demo dashboard without contacting the API", async () => {
    window.history.replaceState({}, "", "/?demo=1");
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    expect(screen.getByRole("status")).toHaveTextContent("Demo workspace");
    expect(screen.getAllByText("Privilege escalation on production cluster")).toHaveLength(2);
    fireEvent.click(screen.getByRole("button", { name: /playbooks/i }));
    expect(screen.getByRole("heading", { name: "Response playbooks" })).toBeInTheDocument();
    expect(screen.getAllByText("Critical endpoint containment")).toHaveLength(2);
    fireEvent.click(screen.getByRole("button", { name: /workflows/i }));
    expect(screen.getByRole("heading", { name: "Workflow runs" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /approve current step/i }));
    await waitFor(() => expect(screen.queryByRole("button", { name: /approve current step/i })).not.toBeInTheDocument());
    expect(screen.getByText("Recovery ready")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /integrations/i }));
    expect(screen.getByRole("heading", { name: "Integrations" })).toBeInTheDocument();
    expect(screen.getByText("ThreatGraph")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("opens the incident creation workflow", () => {
    window.history.replaceState({}, "", "/?demo=1");
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "New incident" }));
    expect(screen.getByRole("dialog", { name: "Create incident" })).toBeInTheDocument();
    expect(screen.getByLabelText("Incident title")).toBeInTheDocument();
  });
});
