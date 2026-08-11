import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { get, isCA, post } from "../api";
import { useAuth } from "../auth";
import { Card, Pill, dateTime } from "../components/ui";

const TAB_FOR: Record<string, string> = {
  GSTR1: "GSTR1",
  PR_RECON: "PR_RECON",
  GSTR3B: "GSTR3B",
};

/* Flat "what needs me" list. Conversations are not browsed here -- each row
   opens the stage that the discussion belongs to. */
export default function Inbox() {
  const { user } = useAuth();
  const ca = isCA(user?.role);
  const [data, setData] = useState<any>(null);
  const [notes, setNotes] = useState<any>(null);
  const [showAll, setShowAll] = useState(false);

  const load = () => {
    get("/api/inbox").then(setData);
    get("/api/notifications?limit=25").then(setNotes);
  };
  useEffect(load, []);

  if (!data) return <div className="empty">Loading…</div>;
  const items = showAll ? data.items : data.items.filter((i: any) => i.mine);

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Needs attention</h1>
          <div className="sub">
            {data.waiting_on_me === 0
              ? "Nothing is waiting on you."
              : `${data.waiting_on_me} item(s) waiting on you.`}
          </div>
        </div>
        <div className="row">
          <button className={showAll ? "" : "primary"} onClick={() => setShowAll(false)}>
            Waiting on me ({data.waiting_on_me})
          </button>
          <button className={showAll ? "primary" : ""} onClick={() => setShowAll(true)}>
            All open ({data.items.length})
          </button>
        </div>
      </div>

      <Card>
        {items.length === 0 && (
          <div className="empty">
            {showAll ? "No open items anywhere." : "Nothing waiting on you right now."}
          </div>
        )}
        {items.length > 0 && (
          <table>
            <thead>
              <tr>
                <th>What</th>
                <th>Where</th>
                <th>Waiting on</th>
                <th>Raised</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {items.map((i: any) => (
                <tr key={i.query_id}>
                  <td>
                    <strong>{i.title}</strong>
                    {i.requires_revision && <div className="sub">A corrected file must be uploaded</div>}
                  </td>
                  <td className="sub">
                    {i.period_label} · {i.return_label ?? i.return_type}
                    {i.invoice_match_id && " · invoice"}
                  </td>
                  <td>
                    <Pill
                      value={i.waiting_on === "CLIENT" ? "ACTION_NEEDED" : "WITH_CA"}
                      label={i.waiting_on === "CLIENT" ? "Client" : "CA team"}
                    />
                  </td>
                  <td className="sub" style={{ whiteSpace: "nowrap" }}>
                    {dateTime(i.created_at)}
                  </td>
                  <td className="num">
                    <Link to={`/cases/${i.case_id}?tab=${TAB_FOR[i.return_type] ?? "overview"}`}>
                      <button className="primary">Open</button>
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      <Card
        title="Recent activity"
        actions={
          notes?.unread_count > 0 ? (
            <button
              onClick={async () => {
                await post("/api/notifications/read-all");
                load();
              }}
            >
              Mark {notes.unread_count} read
            </button>
          ) : undefined
        }
      >
        {(notes?.items ?? []).length === 0 && <div className="empty">Nothing yet.</div>}
        <table>
          <tbody>
            {(notes?.items ?? []).map((n: any) => (
              <tr key={n.id} style={{ opacity: n.is_read ? 0.55 : 1 }}>
                <td style={{ width: 190 }}>
                  <Pill value={n.type} />
                </td>
                <td>
                  {n.title}
                  {n.body && <div className="sub">{n.body}</div>}
                </td>
                <td className="sub" style={{ whiteSpace: "nowrap" }}>
                  {dateTime(n.created_at)}
                </td>
                <td className="num">{n.case_id && <Link to={`/cases/${n.case_id}`}>open →</Link>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      {!ca && (
        <div className="sub" style={{ padding: "0 4px" }}>
          Every message lives on the stage it belongs to — open the month and the conversation is there.
        </div>
      )}
    </>
  );
}
