import { useCallback, useEffect, useState } from "react";
import { get, isCA, post } from "../api";
import { useAuth } from "../auth";
import { dateTime } from "./ui";

/* One discussion per stage (or per mismatched invoice). No thread list, no
   subjects, no separate query screen: a CA message can simply be flagged as
   blocking, and a client reply answers it. */
export default function Discussion({
  returnItemId,
  matchId,
  compact,
  onChange,
}: {
  returnItemId?: number;
  matchId?: number;
  compact?: boolean;
  onChange?: () => void;
}) {
  const { user } = useAuth();
  const ca = isCA(user?.role);
  const base = returnItemId
    ? `/api/return-items/${returnItemId}/discussion`
    : `/api/recon/matches/${matchId}/discussion`;

  const [data, setData] = useState<any>(null);
  const [body, setBody] = useState("");
  const [asQuery, setAsQuery] = useState(false);
  const [needsReupload, setNeedsReupload] = useState(false);
  const [internal, setInternal] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const load = useCallback(() => {
    get(base)
      .then(setData)
      .catch((e) => setErr(e.message));
  }, [base]);

  useEffect(load, [load]);

  async function send() {
    if (!body.trim()) return;
    setBusy(true);
    setErr("");
    try {
      const next = await post(base, {
        body,
        is_internal_note: internal,
        as_query: ca && asQuery,
        requires_revision: needsReupload,
      });
      setData(next);
      setBody("");
      setAsQuery(false);
      setNeedsReupload(false);
      setInternal(false);
      onChange?.();
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function resolve(queryId: number) {
    setBusy(true);
    try {
      setData(await post(`/api/queries/${queryId}/close`));
      onChange?.();
    } finally {
      setBusy(false);
    }
  }

  if (!data) return <div className="empty">Loading…</div>;
  const open = data.open_query;

  return (
    <div>
      {err && <div className="error">{err}</div>}

      {open && (
        <div className={`banner ${open.status === "OPEN" ? "amber" : "blue"}`}>
          <div>
            <strong>
              {open.status === "OPEN"
                ? ca
                  ? "Waiting on the client"
                  : "Action needed from you"
                : ca
                  ? "Client has responded — review and close"
                  : "Sent to your CA team"}
            </strong>
            <div className="sub" style={{ marginTop: 2 }}>
              {open.title}
              {open.requires_revision && " · a corrected file must be uploaded"}
            </div>
          </div>
          {ca && (
            <button className="primary" onClick={() => resolve(open.query_id ?? open.id)} disabled={busy}>
              Mark resolved
            </button>
          )}
        </div>
      )}

      <div className="thread" style={compact ? { maxHeight: 200 } : undefined}>
        {data.messages.length === 0 && (
          <div className="empty">
            No messages yet. {ca ? "Raise a point for the client here." : "Your CA team will write here."}
          </div>
        )}
        {data.messages.map((m: any) => (
          <div
            key={m.id}
            className={`msg ${m.author_user_id === user?.id ? "mine" : ""} ${m.is_internal_note ? "internal" : ""}`}
          >
            <div className="meta">
              <strong>{m.author_name}</strong> · {m.author_role === "CLIENT" ? "Client" : "CA team"} ·{" "}
              {dateTime(m.created_at)}
              {m.is_internal_note && " · internal note"}
            </div>
            <div style={{ whiteSpace: "pre-wrap" }}>{m.body}</div>
          </div>
        ))}
      </div>

      <div style={{ marginTop: 10 }}>
        <textarea
          style={compact ? { minHeight: 56 } : undefined}
          placeholder={ca ? "Write to the client…" : "Reply to your CA team…"}
          value={body}
          onChange={(e) => setBody(e.target.value)}
        />
        <div className="row between" style={{ marginTop: 8 }}>
          <div className="row" style={{ gap: 14 }}>
            {ca && (
              <>
                <label className="sub check">
                  <input
                    type="checkbox"
                    checked={asQuery}
                    onChange={(e) => {
                      setAsQuery(e.target.checked);
                      if (!e.target.checked) setNeedsReupload(false);
                    }}
                  />
                  Needs client action
                </label>
                {asQuery && !matchId && (
                  <label className="sub check">
                    <input
                      type="checkbox"
                      checked={needsReupload}
                      onChange={(e) => setNeedsReupload(e.target.checked)}
                    />
                    Corrected file required
                  </label>
                )}
                <label className="sub check">
                  <input type="checkbox" checked={internal} onChange={(e) => setInternal(e.target.checked)} />
                  Internal note
                </label>
              </>
            )}
          </div>
          <button className="primary" onClick={send} disabled={busy || !body.trim()}>
            {asQuery ? "Send & request action" : "Send"}
          </button>
        </div>
      </div>
    </div>
  );
}
