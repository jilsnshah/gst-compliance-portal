import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { get } from "../api";
import type { CaseSummary } from "../api";
import { Bar, Card, Pill, shortDate } from "../components/ui";

interface DashboardData {
  clients: any[];
  entities: any[];
  cases: CaseSummary[];
  message_count: number;
}

export default function ClientDashboard() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [entityId, setEntityId] = useState<string>("");
  const [error, setError] = useState("");

  useEffect(() => {
    get(`/api/dashboard/client${entityId ? `?entity_id=${entityId}` : ""}`)
      .then(setData)
      .catch((e) => setError(e.message));
  }, [entityId]);

  if (error) return <div className="error">{error}</div>;
  if (!data) return <div className="empty">Loading…</div>;

  return (
    <>
      <div className="page-head">
        <div>
          <h1>{data.clients[0]?.name ?? "My GST compliance"}</h1>
          <div className="sub">
            {data.entities.length} file(s) ·{" "}
            {data.entities.reduce((n, e) => n + e.gstins.length, 0)} GST registration(s)
          </div>
        </div>
        <select style={{ width: 260 }} value={entityId} onChange={(e) => setEntityId(e.target.value)}>
          <option value="">All files</option>
          {data.entities.map((e) => (
            <option key={e.id} value={e.id}>
              {e.legal_name} ({e.file_number})
            </option>
          ))}
        </select>
      </div>

      {data.cases.length === 0 && (
        <div className="card empty">
          No GST months have been opened yet. Your CA team opens each month from their portal.
        </div>
      )}

      <div className="grid cols-2">
        {data.cases.map((c) => (
          <Card key={c.id}>
            <div className="row between">
              <div>
                <h2 style={{ marginBottom: 2 }}>
                  {c.period.label} · {c.entity.trade_name ?? c.entity.legal_name}
                </h2>
                <div className="sub mono">{c.gstin}</div>
              </div>
              <Pill value={c.status} />
            </div>

            <div style={{ margin: "14px 0 4px" }}>
              <div className="row between" style={{ fontSize: 12, color: "var(--muted)" }}>
                <span>Overall progress</span>
                <span>{c.overall_progress}%</span>
              </div>
              <Bar value={c.overall_progress ?? 0} />
            </div>

            <table style={{ marginTop: 12 }}>
              <tbody>
                {c.returns.map((r) => (
                  <tr key={r.id}>
                    <td style={{ width: "42%" }}>{r.return_label}</td>
                    <td>
                      <Pill value={r.client_status} label={r.client_status_label} />
                    </td>
                    <td className="num sub" style={{ whiteSpace: "nowrap" }}>
                      {r.due_date ? `due ${shortDate(r.due_date)}` : ""}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {c.reconciliation && (
              <div className="sub" style={{ marginTop: 10 }}>
                Purchase matching: {c.reconciliation.match_rate}% matched ·{" "}
                {c.reconciliation.action_required} invoice(s) need attention
              </div>
            )}

            <div className="row between" style={{ marginTop: 14 }}>
              <div className="sub">
                {typeof c.documents === "number" ? c.documents : 0} documents · {c.open_queries} open
                {(c.action_required?.length ?? 0) > 0 && (
                  <>
                    {" · "}
                    <span style={{ color: "var(--amber)" }}>
                      Waiting on you: {c.action_required!.join(", ")}
                    </span>
                  </>
                )}
              </div>
              <Link to={`/cases/${c.id}`}>
                <button className="primary">Open month</button>
              </Link>
            </div>
          </Card>
        ))}
      </div>
    </>
  );
}
