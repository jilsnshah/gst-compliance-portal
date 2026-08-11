import type { ReactNode } from "react";

const STATUS_TONE: Record<string, string> = {
  // client-facing
  ACTION_NEEDED: "amber",
  WITH_CA: "blue",
  DONE: "green",
  // internal
  AWAITING_CLIENT_DATA: "amber",
  AWAITING_PAYMENT: "amber",
  CLIENT_DATA_SUBMITTED: "blue",
  UNDER_CA_REVIEW: "blue",
  VERIFIED: "green",
  FILED: "green",
  NOT_STARTED: "",
  COMPLETED: "green",
  IN_PROGRESS: "blue",
  EXACT_MATCH: "green",
  PARTIAL_MATCH: "amber",
  PROBABLE_MATCH: "amber",
  MISMATCH: "red",
  MISSING_IN_2B: "red",
  MISSING_IN_PR: "red",
  OPEN: "amber",
  ANSWERED: "blue",
  RESOLVED: "green",
  CLIENT_RESPONDED: "blue",
  DEFERRED_NEXT_PERIOD: "amber",
  WRITTEN_OFF: "",
  CHALLAN_PENDING: "amber",
  CHALLAN_ISSUED: "amber",
  PAYMENT_CONFIRMED: "green",
  NOT_APPLICABLE: "",
};

export const humanise = (value?: string) =>
  (value ?? "").replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

export function Pill({ value, label }: { value?: string; label?: string }) {
  return <span className={`pill ${STATUS_TONE[value ?? ""] ?? ""}`}>{label ?? humanise(value)}</span>;
}

export function Bar({ value }: { value: number }) {
  return (
    <div className={`bar ${value >= 100 ? "done" : ""}`}>
      <div style={{ width: `${Math.max(value, 2)}%` }} />
    </div>
  );
}

export function Card({ title, actions, children }: { title?: string; actions?: ReactNode; children: ReactNode }) {
  return (
    <div className="card">
      {(title || actions) && (
        <div className="row between" style={{ marginBottom: 12 }}>
          {title && <h2 style={{ margin: 0 }}>{title}</h2>}
          {actions}
        </div>
      )}
      {children}
    </div>
  );
}

export function Stat({ value, label }: { value: ReactNode; label: string }) {
  return (
    <div className="stat">
      <div className="value">{value}</div>
      <div className="label">{label}</div>
    </div>
  );
}

export const money = (n?: number | null) =>
  n === null || n === undefined || Number.isNaN(Number(n))
    ? "—"
    : `₹${Number(n).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

export const shortDate = (value?: string | null) =>
  value ? new Date(value).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" }) : "—";

export const dateTime = (value?: string | null) =>
  value ? new Date(value + (value.endsWith("Z") ? "" : "Z")).toLocaleString("en-IN", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }) : "—";
