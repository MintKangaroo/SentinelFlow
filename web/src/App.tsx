import { useEffect, useState } from "react";

import { fetchReadiness, type Readiness } from "./api";
import "./styles.css";

const runtimeBoundaries = [
  { name: "Control API", role: "FastAPI command boundary" },
  { name: "Workflow Worker", role: "Celery execution boundary" },
  { name: "State Store", role: "PostgreSQL system of record" },
  { name: "Coordination", role: "Redis broker and cache" },
];

export function App() {
  const [readiness, setReadiness] = useState<Readiness | null>(null);
  const [unavailable, setUnavailable] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    fetchReadiness(controller.signal)
      .then(setReadiness)
      .catch(() => setUnavailable(true));
    return () => controller.abort();
  }, []);

  const state = readiness?.status === "ready" ? "Operational" : unavailable ? "Unavailable" : "Checking";

  return (
    <main className="shell">
      <header className="topbar">
        <a className="brand" href="/" aria-label="SentinelFlow home">
          <span className="brand-mark" aria-hidden="true">S</span>
          <span>SentinelFlow</span>
        </a>
        <span className="stage-chip">Foundation · Stage 01</span>
      </header>

      <section className="hero" aria-labelledby="hero-title">
        <div>
          <p className="eyebrow">SECURITY OPERATIONS CONTROL PLANE</p>
          <h1 id="hero-title">One control plane.<br />Every response boundary.</h1>
          <p className="hero-copy">
            SentinelFlow will connect detection, analysis, approval, response,
            validation, and reporting without duplicating the services behind them.
          </p>
        </div>
        <div className={`status-panel status-${state.toLowerCase()}`} role="status">
          <div className="status-heading">
            <span className="pulse" aria-hidden="true" />
            <span>CONTROL PLANE</span>
          </div>
          <strong>{state}</strong>
          <p>{readiness ? `${Object.keys(readiness.checks).length} dependencies connected` : "Verifying runtime dependencies"}</p>
        </div>
      </section>

      <section className="boundaries" aria-labelledby="boundaries-title">
        <div className="section-heading">
          <p className="eyebrow">RUNTIME FOUNDATION</p>
          <h2 id="boundaries-title">Platform boundaries</h2>
        </div>
        <div className="boundary-grid">
          {runtimeBoundaries.map((boundary, index) => (
            <article key={boundary.name}>
              <span className="index">0{index + 1}</span>
              <h3>{boundary.name}</h3>
              <p>{boundary.role}</p>
            </article>
          ))}
        </div>
      </section>

      <footer>
        <span>SentinelFlow v0.1.0</span>
        <span>Domain workflows intentionally deferred</span>
      </footer>
    </main>
  );
}
