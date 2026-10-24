import type { ReactNode } from "react";
import type { HealthStatus } from "./types";

export function StatusBadge({ status }: { status: HealthStatus | string }) {
  return <span className={`badge badge-${status}`}>{status.replace("_", " ")}</span>;
}

export function Stat({ label, value, hint }: { label: string; value: ReactNode; hint?: string }) {
  return (
    <div className="stat">
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      {hint && <div className="stat-hint">{hint}</div>}
    </div>
  );
}

export function Loading() {
  return <p className="muted">Loading…</p>;
}

export function ErrorBox({ message }: { message: string }) {
  return (
    <div className="error-box">
      <strong>Could not load data.</strong> {message}
      <div className="muted">Is the API running? See README → “Run the app”.</div>
    </div>
  );
}

export function Missing({ children = "not provided" }: { children?: ReactNode }) {
  return <span className="missing">{children}</span>;
}
