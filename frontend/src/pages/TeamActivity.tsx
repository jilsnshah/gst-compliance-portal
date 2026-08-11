import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { get, post } from "../api";
import { Card, Pill, dateTime, humanise } from "../components/ui";

/* Staff are not fenced off by client, so this page -- not access control -- is
   how the firm knows who handled which return. */

const RETURN_LABEL: Record<string, string> = {
  GSTR1: "GSTR-1",
  PR_RECON: "Reconciliation",
  GSTR3B: "GSTR-3B",
};

function AddEmployee({ reload }: { reload: () => void }) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ full_name: "", email: "", password: "", designation: "" });
  const [created, setCreated] = useState<{ email: string; password: string } | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  return (
    <Card
      title="Add someone to the team"
      actions={
        <button onClick={() => { setOpen(!open); setCreated(null); setErr(""); }}>
          {open ? "Cancel" : "Add employee"}
        </button>
      }
    >
      {created && (
        <div className="banner blue">
          <div>
            <strong>Employee added</strong>
            <div className="sub">
              Pass these on — the password is not shown again.{" "}
              <span className="mono">{created.email}</span> /{" "}
              <span className="mono">{created.password}</span>
            </div>
          </div>
        </div>
      )}
      {!open && !created && (
        <div className="sub">
          Everyone in the firm sees every client. An account is how their work gets attributed.
        </div>
      )}
      {open && (
        <>
          {err && <div className="error">{err}</div>}
          <div className="row">
            <input
              placeholder="Full name"
              value={form.full_name}
              onChange={(e) => setForm({ ...form, full_name: e.target.value })}
            />
            <input
              placeholder="Email (their login)"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
            />
            <input
              placeholder="Password"
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
            />
            <input
              placeholder="Designation (optional)"
              value={form.designation}
              onChange={(e) => setForm({ ...form, designation: e.target.value })}
            />
            <button
              className="primary"
              disabled={busy || !form.full_name || !form.email || !form.password}
              onClick={async () => {
                setBusy(true);
                setErr("");
                try {
                  await post("/api/users", {
                    full_name: form.full_name,
                    email: form.email,
                    password: form.password,
                    designation: form.designation || null,
                    role: "CA_EMPLOYEE",
                  });
                  setCreated({ email: form.email, password: form.password });
                  setForm({ full_name: "", email: "", password: "", designation: "" });
                  setOpen(false);
                  reload();
                } catch (e: any) {
                  setErr(e.message);
                } finally {
                  setBusy(false);
                }
              }}
            >
              Create login
            </button>
          </div>
        </>
      )}
    </Card>
  );
}

export default function TeamActivity() {
  const [data, setData] = useState<any>(null);
  const [days, setDays] = useState(30);
  const [q, setQ] = useState("");
  const [err, setErr] = useState("");

  useEffect(() => {
    const t = setTimeout(() => {
      get(`/api/dashboard/employees?days=${days}${q.trim() ? `&q=${encodeURIComponent(q.trim())}` : ""}`)
        .then(setData)
        .catch((e) => setErr(e.message));
    }, q ? 250 : 0);
    return () => clearTimeout(t);
  }, [days, q]);

  if (err) return <div className="error">{err}</div>;
  if (!data) return <div className="empty">Loading…</div>;

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Team activity</h1>
          <div className="sub">
            Everyone can see every client. This is how the firm knows who did what.
          </div>
        </div>
        <div className="row">
        <input
          style={{ width: 220 }}
          placeholder="Find someone…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <select style={{ width: 160 }} value={days} onChange={(e) => setDays(Number(e.target.value))}>
          <option value={7}>Last 7 days</option>
          <option value={30}>Last 30 days</option>
          <option value={90}>Last 90 days</option>
          <option value={3650}>All time</option>
        </select>
        </div>
      </div>

      <AddEmployee reload={() => setQ((v) => v)} />

      <Card title={`People (${data.total ?? data.employees.length})`}>
        <table>
          <thead>
            <tr>
              <th>Who</th>
              <th className="num">Uploads</th>
              <th className="num">Status moves</th>
              <th className="num">Queries</th>
              <th className="num">Recons</th>
              <th className="num">Filings</th>
              <th className="num">Total</th>
              <th>Last active</th>
            </tr>
          </thead>
          <tbody>
            {data.employees.map((e: any) => (
              <tr key={e.employee_id}>
                <td>
                  <strong>{e.name}</strong>
                  <div className="sub">
                    {e.designation ?? e.role?.replace(/_/g, " ")} · {e.email}
                  </div>
                </td>
                <td className="num">{e.counts.uploads}</td>
                <td className="num">{e.counts.status_changes}</td>
                <td className="num">{e.counts.queries_raised + e.counts.queries_resolved}</td>
                <td className="num">{e.counts.reconciliations}</td>
                <td className="num">{e.counts.filings}</td>
                <td className="num">
                  <strong>{e.counts.total}</strong>
                </td>
                <td className="sub" style={{ whiteSpace: "nowrap" }}>
                  {e.last_active ? dateTime(e.last_active) : "never"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <Card title="Currently in hand">
        <p className="sub" style={{ marginTop: 0 }}>
          Returns someone has picked up and not yet finished, taken from who actually started the
          review rather than a nominal assignment.
        </p>
        {data.employees.every((e: any) => e.in_hand.length === 0) && (
          <div className="empty">Nobody has a return open right now.</div>
        )}
        {data.employees
          .filter((e: any) => e.in_hand.length > 0)
          .map((e: any) => (
            <div key={e.employee_id} style={{ marginBottom: 14 }}>
              <h3 style={{ marginBottom: 6 }}>
                {e.name} — {e.in_hand.length} open
              </h3>
              <table>
                <thead>
                  <tr>
                    <th>File</th>
                    <th>GSTIN</th>
                    <th>Period</th>
                    <th>Return</th>
                    <th>Status</th>
                    <th>Since</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {e.in_hand.map((r: any, i: number) => (
                    <tr key={i}>
                      <td>{r.file_number}</td>
                      <td className="mono">{r.gstin}</td>
                      <td>{r.period}</td>
                      <td>{RETURN_LABEL[r.return_type] ?? r.return_type}</td>
                      <td>
                        <Pill value={r.status} label={humanise(r.status)} />
                      </td>
                      <td className="sub" style={{ whiteSpace: "nowrap" }}>
                        {dateTime(r.since)}
                      </td>
                      <td className="num">
                        <Link to={`/cases/${r.case_id}`}>Open</Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
      </Card>

      <Card title="Recent actions">
        <table>
          <thead>
            <tr>
              <th>When</th>
              <th>Who</th>
              <th>Action</th>
              <th>What</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {data.recent.map((a: any) => (
              <tr key={a.id}>
                <td className="sub" style={{ whiteSpace: "nowrap" }}>
                  {dateTime(a.created_at)}
                </td>
                <td>{a.actor_name}</td>
                <td>
                  <Pill value={a.action} />
                </td>
                <td>{a.description}</td>
                <td className="num">{a.case_id && <Link to={`/cases/${a.case_id}`}>open →</Link>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </>
  );
}
