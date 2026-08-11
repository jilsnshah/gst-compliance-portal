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
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");

  const load = () => {
    get("/api/clients").then(setClients);
    get("/api/entities").then(setEntities);
    get("/api/employees").then(setEmployees).catch(() => {});
  };
  useEffect(load, []);

  async function openMonth(entityId: number, year: number, month: number) {
    setErr("");
    setMsg("");
    try {
      const c = await post("/api/cases", { entity_id: entityId, year, month });
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
        <Card key={client.id} title={client.name}>
          <div className="sub" style={{ marginBottom: 12 }}>
            Signs in as <span className="mono">{client.email ?? "— no login —"}</span>
            {client.phone && ` · ${client.phone}`}
          </div>
          {entities
            .filter((e) => e.client_id === client.id)
            .map((entity) => (
              <div key={entity.id} style={{ borderTop: "1px solid var(--border)", paddingTop: 12, marginTop: 12 }}>
                <div className="row between">
                  <div>
                    <strong>{entity.legal_name}</strong>
                    {entity.trade_name && <span className="sub"> · trading as {entity.trade_name}</span>}
                    <div className="mono" style={{ marginTop: 2 }}>{entity.gstin}</div>
                    <div className="sub">
                      File {entity.file_number} · PAN <span className="mono">{entity.pan}</span> ·{" "}
                      {humanise(entity.constitution)} · {entity.state_name ?? entity.state ?? "—"} ·{" "}
                      {humanise(entity.filing_frequency)} ·{" "}
                      {employees.find((e) => e.id === entity.assigned_employee_id)?.full_name ?? "unassigned"}
                    </div>
                  </div>
                  <OpenMonth onOpen={(y, m) => openMonth(entity.id, y, m)} />
                </div>
              </div>
            ))}
        </Card>
      ))}

      {user?.role === "CA_ADMIN" && <NewClientForms reload={load} clients={clients} />}
    </>
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

function NewClientForms({ reload, clients }: { reload: () => void; clients: any[] }) {
  const [client, setClient] = useState({ name: "", email: "", password: "", phone: "" });
  const [file, setFile] = useState({
    client_id: "",
    file_number: "",
    legal_name: "",
    pan: "",
    gstin: "",
    state_name: "",
  });
  const [err, setErr] = useState("");
  const [created, setCreated] = useState<{ email: string; password: string } | null>(null);

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
    <Card title="Add a client or a file">
      {err && <div className="error">{err}</div>}
      {created && (
        <div className="banner blue" style={{ marginBottom: 12 }}>
          <div>
            <strong>Client created</strong>
            <div className="sub">
              Send these over — the password is not shown again.{" "}
              <span className="mono">{created.email}</span> / <span className="mono">{created.password}</span>
            </div>
          </div>
        </div>
      )}

      <div className="grid cols-2">
        <div className="upload-box">
          <h3>New client</h3>
          <div className="sub" style={{ marginBottom: 8 }}>
            This also creates the login they sign in with.
          </div>
          <div className="field">
            <input placeholder="Name" value={client.name} onChange={(e) => setClient({ ...client, name: e.target.value })} />
          </div>
          <div className="field">
            <input placeholder="Email (their login)" value={client.email} onChange={(e) => setClient({ ...client, email: e.target.value })} />
          </div>
          <div className="field">
            <input placeholder="Phone" value={client.phone} onChange={(e) => setClient({ ...client, phone: e.target.value })} />
          </div>
          <div className="field">
            <input placeholder="Password" value={client.password} onChange={(e) => setClient({ ...client, password: e.target.value })} />
          </div>
          <button
            disabled={!client.name || !client.email || !client.password}
            onClick={() =>
              run(async () => {
                await post("/api/clients", { ...client, phone: client.phone || null });
                setCreated({ email: client.email, password: client.password });
                setClient({ name: "", email: "", password: "", phone: "" });
              })
            }
          >
            Create client
          </button>
        </div>

        <div className="upload-box">
          <h3>New file</h3>
          <div className="sub" style={{ marginBottom: 8 }}>
            One file per GST registration. A client with two GSTINs gets two files.
          </div>
          <div className="field">
            <select value={file.client_id} onChange={(e) => setFile({ ...file, client_id: e.target.value })}>
              <option value="">Select client</option>
              {clients.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <input placeholder="File number" value={file.file_number} onChange={(e) => setFile({ ...file, file_number: e.target.value })} />
          </div>
          <div className="field">
            <input placeholder="Legal name" value={file.legal_name} onChange={(e) => setFile({ ...file, legal_name: e.target.value })} />
          </div>
          <div className="field">
            <input placeholder="PAN (10 chars)" value={file.pan} onChange={(e) => setFile({ ...file, pan: e.target.value.toUpperCase() })} />
          </div>
          <div className="field">
            <input placeholder="GSTIN (15 chars)" value={file.gstin} onChange={(e) => setFile({ ...file, gstin: e.target.value.toUpperCase() })} />
          </div>
          <div className="field">
            <input placeholder="State" value={file.state_name} onChange={(e) => setFile({ ...file, state_name: e.target.value })} />
          </div>
          <button
            disabled={!file.client_id || !file.file_number || !file.legal_name || file.pan.length !== 10 || file.gstin.length !== 15}
            onClick={() =>
              run(async () => {
                await post("/api/entities", { ...file, client_id: Number(file.client_id) });
                setFile({ client_id: "", file_number: "", legal_name: "", pan: "", gstin: "", state_name: "" });
              })
            }
          >
            Create file
          </button>
        </div>
      </div>
    </Card>
  );
}
