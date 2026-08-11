import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { get, post } from "../api";
import { useAuth } from "../auth";
import { Card, humanise } from "../components/ui";

export default function Clients() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [entities, setEntities] = useState<any[]>([]);
  const [clients, setClients] = useState<any[]>([]);
  const [employees, setEmployees] = useState<any[]>([]);
  const [logins, setLogins] = useState<any[]>([]);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");

  const load = () => {
    get("/api/clients").then(setClients);
    get("/api/entities").then(setEntities);
    get("/api/employees").then(setEmployees).catch(() => {});
    get("/api/users").then(setLogins).catch(() => {});
  };
  useEffect(load, []);

  async function openMonth(gstRegistrationId: number, year: number, month: number) {
    setErr("");
    setMsg("");
    try {
      const c = await post("/api/cases", { gst_registration_id: gstRegistrationId, year, month });
      setMsg(`${c.period.label} opened for ${c.gstin}`);
      navigate(`/cases/${c.id}`);
    } catch (e: any) {
      setErr(e.message);
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Clients &amp; files</h1>
          <div className="sub">
            A client owns files (entities); each file owns one or more GSTINs. Compliance months hang off the GSTIN.
          </div>
        </div>
      </div>

      {err && <div className="error">{err}</div>}
      {msg && <div className="card sub">{msg}</div>}

      {clients.map((client) => (
        <Card key={client.id} title={`${client.name} (${client.client_code})`}>
          <div className="sub" style={{ marginBottom: 10 }}>
            {client.primary_email} · {client.primary_phone ?? "no phone"}
          </div>

          <ClientLogins
            client={client}
            logins={logins.filter((u) => u.client_ids.includes(client.id))}
            isAdmin={user?.role === "CA_ADMIN"}
            reload={load}
          />
          {entities
            .filter((e) => e.client_id === client.id)
            .map((entity) => (
              <div key={entity.id} style={{ borderTop: "1px solid var(--border)", paddingTop: 12, marginTop: 12 }}>
                <div className="row between">
                  <div>
                    <strong>{entity.legal_name}</strong>
                    {entity.trade_name && <span className="sub"> · trading as {entity.trade_name}</span>}
                    <div className="sub">
                      File {entity.file_number} · PAN <span className="mono">{entity.pan}</span> ·{" "}
                      {humanise(entity.constitution)} · {entity.city ?? "—"}, {entity.address?.state ?? entity.state ?? "—"}
                    </div>
                  </div>
                  <div className="sub">{(entity.applicable_services ?? []).join(", ")}</div>
                </div>

                <table style={{ marginTop: 10 }}>
                  <thead>
                    <tr>
                      <th>GSTIN</th>
                      <th>State</th>
                      <th>Frequency</th>
                      <th>Owner</th>
                      <th className="num">Open a month</th>
                    </tr>
                  </thead>
                  <tbody>
                    {entity.registrations.map((reg: any) => (
                      <tr key={reg.id}>
                        <td className="mono">{reg.gstin}</td>
                        <td>{reg.state_name ?? "—"}</td>
                        <td className="sub">{humanise(reg.filing_frequency)}</td>
                        <td className="sub">
                          {employees.find((e) => e.id === reg.assigned_employee_id)?.full_name ?? "unassigned"}
                        </td>
                        <td className="num">
                          <OpenMonth onOpen={(y, m) => openMonth(reg.id, y, m)} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
        </Card>
      ))}

      {user?.role === "CA_ADMIN" && <NewClientForms reload={load} clients={clients} entities={entities} />}
    </>
  );
}

function ClientLogins({
  client,
  logins,
  isAdmin,
  reload,
}: {
  client: any;
  logins: any[];
  isAdmin: boolean;
  reload: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ full_name: "", email: "", password: "" });
  const [err, setErr] = useState("");
  const [created, setCreated] = useState<{ email: string; password: string } | null>(null);

  return (
    <div className="upload-box" style={{ marginBottom: 12 }}>
      <div className="row between">
        <div>
          <h3 style={{ marginBottom: 4 }}>Portal access</h3>
          {logins.length === 0 ? (
            <span style={{ color: "var(--amber)" }}>
              Nobody can sign in for this client yet.
            </span>
          ) : (
            <span className="sub">
              {logins.map((u) => `${u.full_name} (${u.email})`).join(" · ")}
            </span>
          )}
        </div>
        {isAdmin && (
          <button onClick={() => { setOpen(!open); setCreated(null); }}>
            {open ? "Cancel" : "Add a login"}
          </button>
        )}
      </div>

      {created && (
        <div className="banner blue" style={{ marginTop: 10 }}>
          <div>
            <strong>Login created</strong>
            <div className="sub">
              Send these to the client — the password is not shown again.
              <br />
              <span className="mono">{created.email}</span> · password{" "}
              <span className="mono">{created.password}</span>
            </div>
          </div>
        </div>
      )}

      {open && (
        <div style={{ marginTop: 10 }}>
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
              placeholder="Temporary password"
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
            />
            <button
              className="primary"
              disabled={!form.full_name || !form.email || !form.password}
              onClick={async () => {
                setErr("");
                try {
                  await post("/api/users", {
                    ...form,
                    role: "CLIENT",
                    client_id: client.id,
                  });
                  setCreated({ email: form.email, password: form.password });
                  setForm({ full_name: "", email: "", password: "" });
                  setOpen(false);
                  reload();
                } catch (e: any) {
                  setErr(e.message);
                }
              }}
            >
              Create login
            </button>
          </div>
          <div className="sub" style={{ marginTop: 6 }}>
            They sign in with this email and password. There is no invitation email yet, so pass the
            details on yourself.
          </div>
        </div>
      )}
    </div>
  );
}

function OpenMonth({ onOpen }: { onOpen: (year: number, month: number) => void }) {
  const now = new Date();
  const [year, setYear] = useState(String(now.getFullYear()));
  const [month, setMonth] = useState(String(now.getMonth() + 1));
  return (
    <div className="row" style={{ justifyContent: "flex-end" }}>
      <select value={month} onChange={(e) => setMonth(e.target.value)} style={{ width: 120 }}>
        {Array.from({ length: 12 }, (_, i) => (
          <option key={i + 1} value={i + 1}>
            {new Date(2000, i, 1).toLocaleString("en", { month: "short" })}
          </option>
        ))}
      </select>
      <input value={year} onChange={(e) => setYear(e.target.value)} style={{ width: 80 }} />
      <button onClick={() => onOpen(Number(year), Number(month))}>Open</button>
    </div>
  );
}

function NewClientForms({ reload, clients, entities }: { reload: () => void; clients: any[]; entities: any[] }) {
  const [client, setClient] = useState({ client_code: "", name: "", primary_email: "" });
  const [entity, setEntity] = useState({ client_id: "", file_number: "", legal_name: "", pan: "" });
  const [gstin, setGstin] = useState({ entity_id: "", gstin: "", state_name: "" });
  const [err, setErr] = useState("");

  const run = async (fn: () => Promise<unknown>) => {
    setErr("");
    try {
      await fn();
      reload();
    } catch (e: any) {
      setErr(e.message);
    }
  };

  return (
    <Card title="Add masters">
      {err && <div className="error">{err}</div>}
      <div className="grid cols-3">
        <div className="upload-box">
          <h3>New client</h3>
          <div className="field">
            <input placeholder="Client code" value={client.client_code} onChange={(e) => setClient({ ...client, client_code: e.target.value })} />
          </div>
          <div className="field">
            <input placeholder="Name" value={client.name} onChange={(e) => setClient({ ...client, name: e.target.value })} />
          </div>
          <div className="field">
            <input placeholder="Email" value={client.primary_email} onChange={(e) => setClient({ ...client, primary_email: e.target.value })} />
          </div>
          <button onClick={() => run(() => post("/api/clients", { ...client, primary_email: client.primary_email || null }))}>
            Create client
          </button>
        </div>

        <div className="upload-box">
          <h3>New file / entity</h3>
          <div className="field">
            <select value={entity.client_id} onChange={(e) => setEntity({ ...entity, client_id: e.target.value })}>
              <option value="">Select client</option>
              {clients.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <input placeholder="File number" value={entity.file_number} onChange={(e) => setEntity({ ...entity, file_number: e.target.value })} />
          </div>
          <div className="field">
            <input placeholder="Legal name" value={entity.legal_name} onChange={(e) => setEntity({ ...entity, legal_name: e.target.value })} />
          </div>
          <div className="field">
            <input placeholder="PAN (10 chars)" value={entity.pan} onChange={(e) => setEntity({ ...entity, pan: e.target.value.toUpperCase() })} />
          </div>
          <button onClick={() => run(() => post("/api/entities", { ...entity, client_id: Number(entity.client_id) }))}>
            Create file
          </button>
        </div>

        <div className="upload-box">
          <h3>New GSTIN</h3>
          <div className="field">
            <select value={gstin.entity_id} onChange={(e) => setGstin({ ...gstin, entity_id: e.target.value })}>
              <option value="">Select file</option>
              {entities.map((e) => (
                <option key={e.id} value={e.id}>
                  {e.legal_name} ({e.file_number})
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <input placeholder="GSTIN (15 chars)" value={gstin.gstin} onChange={(e) => setGstin({ ...gstin, gstin: e.target.value.toUpperCase() })} />
          </div>
          <div className="field">
            <input placeholder="State" value={gstin.state_name} onChange={(e) => setGstin({ ...gstin, state_name: e.target.value })} />
          </div>
          <button onClick={() => run(() => post("/api/gstins", { ...gstin, entity_id: Number(gstin.entity_id) }))}>
            Add GSTIN
          </button>
        </div>
      </div>
    </Card>
  );
}
