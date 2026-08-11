import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { get } from "../api";
import type { CaseSummary } from "../api";
import { Card, Pill, Stat, humanise, shortDate } from "../components/ui";

const BUCKETS = [
  ["awaiting_data", "Awaiting data"],
  ["to_review", "To review"],
  ["waiting_on_client", "Waiting on client"],
  ["awaiting_payment", "Awaiting payment"],
  ["ready_to_file", "Ready to file"],
  ["done", "Done"],
] as const;

const LABELS: Record<string, string> = {
  GSTR1: "GSTR-1",
  PR_RECON: "Purchase reconciliation",
  GSTR3B: "GSTR-3B",
};

export default function CaDashboard() {
  const [dash, setDash] = useState<any>(null);
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [employees, setEmployees] = useState<any[]>([]);
  const [clients, setClients] = useState<any[]>([]);
  const [filters, setFilters] = useState({ year: "", month: "", employee_id: "", client_id: "", return_status: "" });
  const [error, setError] = useState("");

  const query = (extra: Record<string, string> = {}) => {
    const params = new URLSearchParams();
    Object.entries({ ...filters, ...extra }).forEach(([k, v]) => v && params.set(k, v));
    const qs = params.toString();
    return qs ? `?${qs}` : "";
  };

  useEffect(() => {
    Promise.all([get("/api/employees"), get("/api/clients")])
      .then(([e, c]) => {
        setEmployees(e);
        setClients(c);
      })
      .catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    get(`/api/dashboard/ca${query()}`).then(setDash).catch((e) => setError(e.message));
    get(`/api/cases${query()}`).then(setCases).catch((e) => setError(e.message));
  }, [filters]);

  if (error) return <div className="error">{error}</div>;
  if (!dash) return <div className="empty">Loading…</div>;

  const set = (k: string) => (e: React.ChangeEvent<HTMLSelectElement | HTMLInputElement>) =>
    setFilters((f) => ({ ...f, [k]: e.target.value }));

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Today's work</h1>
          <div className="sub">Every open return track across the clients you can see.</div>
        </div>
      </div>

      <div className="grid cols-3" style={{ marginBottom: 16 }}>
        <Stat value={dash.totals.return_items} label="Return tracks in scope" />
        <Stat value={dash.totals.overdue} label="Overdue" />
        <Stat value={dash.totals.open_queries} label="Open queries" />
        <Stat value={dash.totals.unresolved_mismatches} label="Unresolved mismatches" />
      </div>

      <Card title="Filters">
        <div className="row">
          <input placeholder="Year (e.g. 2026)" style={{ width: 140 }} value={filters.year} onChange={set("year")} />
          <select style={{ width: 150 }} value={filters.month} onChange={set("month")}>
            <option value="">All months</option>
            {Array.from({ length: 12 }, (_, i) => (
              <option key={i + 1} value={i + 1}>
                {new Date(2000, i, 1).toLocaleString("en", { month: "long" })}
              </option>
            ))}
          </select>
          <select style={{ width: 200 }} value={filters.employee_id} onChange={set("employee_id")}>
            <option value="">All employees</option>
            {employees.map((e) => (
              <option key={e.id} value={e.id}>
                {e.full_name}
              </option>
            ))}
          </select>
          <select style={{ width: 200 }} value={filters.client_id} onChange={set("client_id")}>
            <option value="">All clients</option>
            {clients.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
          <button className="ghost" onClick={() => setFilters({ year: "", month: "", employee_id: "", client_id: "", return_status: "" })}>
            Clear
          </button>
        </div>
      </Card>

      <Card title="Work queue">
        <table>
          <thead>
            <tr>
              <th>Return</th>
              {BUCKETS.map(([key, label]) => (
                <th key={key} className="num">
                  {label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {Object.entries(dash.work).map(([rt, buckets]: [string, any]) => (
              <tr key={rt}>
                <td>
                  <strong>{LABELS[rt] ?? rt}</strong>
                </td>
                {BUCKETS.map(([key]) => (
                  <td key={key} className="num" style={{ color: buckets[key] ? undefined : "var(--muted)" }}>
                    {buckets[key]}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      {dash.overdue_items.length > 0 && (
        <Card title="Overdue">
          <table>
            <thead>
              <tr>
                <th>Return</th>
                <th>Status</th>
                <th>Due</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {dash.overdue_items.map((i: any) => (
                <tr key={i.return_item_id}>
                  <td>{LABELS[i.return_type] ?? i.return_type}</td>
                  <td>
                    <Pill value={i.status} />
                  </td>
                  <td style={{ color: "var(--red)" }}>{shortDate(i.due_date)}</td>
                  <td className="num">
                    <Link to={`/cases/${i.case_id}`}>Open</Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      <Card title={`Compliance months (${cases.length})`}>
        <table>
          <thead>
            <tr>
              <th>Client</th>
              <th>GSTIN</th>
              <th>Period</th>
              <th>GSTR-1</th>
              <th>Reconciliation</th>
              <th>GSTR-3B</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {cases.map((c) => {
              const byType = Object.fromEntries(c.returns.map((r) => [r.return_type, r]));
              return (
                <tr key={c.id}>
                  <td>
                    <strong>{c.client.name}</strong>
                    <div className="sub">{c.entity.legal_name}</div>
                  </td>
                  <td className="mono">{c.gstin}</td>
                  <td>{c.period.label}</td>
                  {(["GSTR1", "PR_RECON", "GSTR3B"] as const).map((rt) => (
                    <td key={rt}>
                      <Pill value={byType[rt]?.status} label={humanise(byType[rt]?.status)} />
                      {byType[rt]?.status === "UNDER_CA_REVIEW" && byType[rt]?.review_started_by && (
                        <div className="sub">{byType[rt].review_started_by}</div>
                      )}
                    </td>
                  ))}
                  <td className="num">
                    <Link to={`/cases/${c.id}`}>Open</Link>
                  </td>
                </tr>
              );
            })}
            {cases.length === 0 && (
              <tr>
                <td colSpan={7} className="empty">
                  No compliance months match these filters.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </Card>
    </>
  );
}
