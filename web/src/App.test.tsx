import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";

describe("App", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("shows the connected foundation state", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ status: "ready", checks: { database: "ok", redis: "ok" } }),
    }));

    render(<App />);

    expect(screen.getByRole("heading", { name: /one control plane/i })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Operational"));
    expect(screen.getByRole("status")).toHaveTextContent("2 dependencies connected");
  });

  it("shows an unavailable state when readiness fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));

    render(<App />);

    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Unavailable"));
  });
});
