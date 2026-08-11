import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { get, post } from "../api";
import { Card } from "../components/ui";

/* The firm's main working screen: find a file, then open it.

   A CA looks a file up by whatever they happen to have in front of them -- a
   client's name, a file number, a GSTIN, a PAN -- so it is one search box over
   all of them rather than a field each. Picking a month is a step later, on the
   file's own page, because you rarely know which month you want until you have
   seen the year. */
export default function Clients() {
  const navigate = useNavigate();
  const [entities, setEntities] = useState<any[]>([]);
  const [clients, setClients] = useState<any[]>([]);
  const [employees, setEmployees] = useState<any[]>([]);
  const [q, setQ] = useState("");
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const [searched, setSearched] = useState(false);
  const [year, setYear] = useState("");
  const [month, setMonth] = useState("");
  const [err, setErr] = useState("");

  const load = () => {
    get("/api/clients").then(setClients).catch(() => {});
    get("/api/employees").then(setEmployees).catch(() => {});
    const params = new URLSearchParams();
    if (q.trim()) params.set("q", q.trim());
    if (year) params.set("year", year);
    if (month) params.set("month", month);
    const qs = params.toString();
    get(`/api/entities?${qs}${qs ? "&" : ""}limit=50&offset=${offset}`)
      .then((r) => {
        setEntities(r.items ?? []);
        setTotal(r.total ?? 0);
        setSearched(r.searched ?? false);
      })
      .catch((e) => setErr(e.message));
  };

  // Debounced so typing does not fire a request per keystroke.
  useEffect(() => {
    const t = setTimeout(load, q ? 250 : 0);
    return () => clearTimeout(t);
  }, [q, year, month, offset]);

  // A new search always starts from the first page.
  useEffect(() => setOffset(0), [q, year, month]);

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Clients &amp; files</h1>
          <div className="sub">
            One file is one GST registration. Open a file to see its whole year.
          </div>
        </div>
      </div>

      {err && <div className="error">{err}</div>}

      <Card>
        <div className="row">
          <input
            style={{ flex: 2, minWidth: 260 }}
            placeholder="Search client, file number, GSTIN, PAN or trade name…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
          <input
            style={{ width: 110 }}
            placeholder="Year"
            value={year}
            onChange={(e) => setYear(e.target.value)}
          />
          <select style={{ width: 150 }} value={month} onChange={(e) => setMonth(e.target.value)}>
            <option value="">Any month</option>
            {Array.from({ length: 12 }, (_, i) => (
              <option key={i + 1} value={i + 1}>
                {new Date(2000, i, 1).toLocaleString("en", { month: "long" })}
              </option>
            ))}
          </select>
          {(q || year || month) && (
            <button
              className="ghost"
              onClick={() => {
                setQ("");
                setYear("");
                setMonth("");
              }}
            >
              Clear
            </button>
          )}
        </div>
        <div className="sub" style={{ marginTop: 8 }}>
          {searched ? (
            <>
              {total} file{total === 1 ? "" : "s"} match
              {(year || month) && " that filter"}
              {total > entities.length && ` — showing ${offset + 1}–${offset + entities.length}`}
            </>
          ) : (
            <>Most recently worked on. Search to find any of the {total} files.</>
          )}
        </div>
      </Card>

      <Card>
        <table>
          <thead>
            <tr>
              <th>File</th>
              <th>GSTIN</th>
              <th>PAN</th>
              <th>Client</th>
              <th>State</th>
              <th>Handler</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {entities.map((e) => (
              <tr key={e.id}>
                <td>
                  <strong>{e.legal_name}</strong>
                  <div className="sub">
                    {e.file_number}
                    {e.trade_name && ` · ${e.trade_name}`}
                  </div>
                </td>
                <td className="mono">{e.gstin}</td>
                <td className="mono">{e.pan}</td>
                <td>{e.client_name ?? clients.find((c) => c.id === e.client_id)?.name}</td>
                <td className="sub">{e.state_name ?? e.address?.state ?? "—"}</td>
                <td className="sub">
                  {employees.find((x) => x.id === e.assigned_employee_id)?.full_name ?? "—"}
                </td>
                <td className="num">
                  <button className="primary" onClick={() => navigate(`/ca/files/${e.id}`)}>
                    Open file
                  </button>
                </td>
              </tr>
            ))}
            {entities.length === 0 && (
              <tr>
                <td colSpan={7} className="empty">
                  {searched ? "Nothing matches that search." : "No files yet."}
                </td>
              </tr>
            )}
          </tbody>
        </table>
        {total > entities.length && (
          <div className="row between" style={{ marginTop: 12 }}>
            <button disabled={offset === 0} onClick={() => setOffset(Math.max(offset - 50, 0))}>
              ← Previous
            </button>
            <span className="sub">
              {offset + 1}–{offset + entities.length} of {total}
            </span>
            <button
              disabled={offset + entities.length >= total}
              onClick={() => setOffset(offset + 50)}
            >
              Next →
            </button>
          </div>
        )}
      </Card>

      <NewClientForms reload={load} clients={clients} />
    </>
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
