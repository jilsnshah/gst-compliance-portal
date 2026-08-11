import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { get } from "../api";
import { Card, Pill, dateTime } from "../components/ui";

export default function AuditTrail() {
  const [logs, setLogs] = useState<any[]>([]);
  const [clients, setClients] = useState<any[]>([]);
  const [clientId, setClientId] = useState("");

  useEffect(() => {
    get("/api/clients").then(setClients);
  }, []);

  useEffect(() => {
    get(`/api/dashboard/audit?limit=200${clientId ? `&client_id=${clientId}` : ""}`).then(setLogs);
  }, [clientId]);

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Audit trail</h1>
          <div className="sub">Every upload, status change, query, reconciliation and filing across the firm.</div>
        </div>
        <select style={{ width: 240 }} value={clientId} onChange={(e) => setClientId(e.target.value)}>
          <option value="">All clients</option>
          {clients.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
      </div>

      <Card>
        <table>
          <thead>
            <tr>
              <th>When</th>
              <th>Who</th>
              <th>Action</th>
              <th>Detail</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {logs.map((l) => (
              <tr key={l.id}>
                <td className="sub" style={{ whiteSpace: "nowrap" }}>
                  {dateTime(l.created_at)}
                </td>
                <td>
                  {l.actor_name}
                  <div className="sub">{l.actor_role?.replace(/_/g, " ")}</div>
                </td>
                <td>
                  <Pill value={l.action} />
                </td>
                <td>{l.description}</td>
                <td className="num">{l.case_id && <Link to={`/cases/${l.case_id}`}>month →</Link>}</td>
              </tr>
            ))}
            {logs.length === 0 && (
              <tr>
                <td colSpan={5} className="empty">
                  No activity recorded yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </Card>
    </>
  );
}
