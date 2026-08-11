import { useCallback, useEffect, useState } from "react";
import { download, get, isCA, post, upload } from "../api";
import { useAuth } from "../auth";
import { dateTime } from "./ui";

/* One discussion per stage (or per mismatched invoice). No thread list, no
   subjects, no separate query screen: a CA message can simply be flagged as
   blocking, and a client reply answers it. */
interface Attachment {
  document_version_id: number;
  filename: string;
  size_bytes: number;
  content_type?: string;
  download_url: string;
}

const isImage = (a: { content_type?: string; filename?: string }) =>
  (a.content_type ?? "").startsWith("image/") ||
  /\.(png|jpe?g|gif|webp|heic)$/i.test(a.filename ?? "");

const readableSize = (n?: number) =>
  !n ? "" : n < 1024 * 1024 ? `${Math.round(n / 1024)} KB` : `${(n / 1024 / 1024).toFixed(1)} MB`;

export default function Discussion({
  returnItemId,
  matchId,
  caseId,
  compact,
  onChange,
}: {
  returnItemId?: number;
  matchId?: number;
  caseId: number;
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
  const [uploading, setUploading] = useState(false);
  const [pending, setPending] = useState<Attachment[]>([]);
  const [err, setErr] = useState("");

  const load = useCallback(() => {
    get(base)
      .then(setData)
      .catch((e) => setErr(e.message));
  }, [base]);

  useEffect(load, [load]);

  async function attach(files: FileList | null) {
    if (!files?.length) return;
    setUploading(true);
    setErr("");
    try {
      for (const file of Array.from(files)) {
        const form = new FormData();
        form.append("file", file);
        const res = await upload(`/api/cases/${caseId}/attachments`, form);
        setPending((p) => [...p, res]);
      }
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setUploading(false);
    }
  }

  async function send() {
    if (!body.trim() && pending.length === 0) return;
    setBusy(true);
    setErr("");
    try {
      const next = await post(base, {
        body: body.trim() || (pending.length === 1 ? pending[0].filename : "Attached files"),
        is_internal_note: internal,
        as_query: ca && asQuery,
        requires_revision: needsReupload,
        document_version_ids: pending.map((a) => a.document_version_id),
      });
      setData(next);
      setBody("");
      setPending([]);
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
            {(m.attachments ?? []).length > 0 && (
              <div className="row" style={{ marginTop: 8, gap: 8 }}>
                {m.attachments.map((a: Attachment) => (
                  <button
                    key={a.document_version_id}
                    className="attachment"
                    title={`${a.filename} · ${readableSize(a.size_bytes)}`}
                    onClick={() => download(a.download_url, a.filename)}
                  >
                    <span>{isImage(a) ? "🖼" : "📎"}</span>
                    <span className="attachment-name">{a.filename}</span>
                    <span className="sub">{readableSize(a.size_bytes)}</span>
                  </button>
                ))}
              </div>
            )}
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
        {pending.length > 0 && (
          <div className="row" style={{ gap: 8, marginTop: 8 }}>
            {pending.map((a) => (
              <span key={a.document_version_id} className="attachment">
                <span>{isImage(a) ? "🖼" : "📎"}</span>
                <span className="attachment-name">{a.filename}</span>
                <button
                  className="ghost"
                  style={{ padding: "0 4px" }}
                  onClick={() =>
                    setPending((p) =>
                      p.filter((x) => x.document_version_id !== a.document_version_id),
                    )
                  }
                >
                  ×
                </button>
              </span>
            ))}
          </div>
        )}
        <div className="row between" style={{ marginTop: 8 }}>
          <div className="row" style={{ gap: 14 }}>
            <label className="sub check" style={{ cursor: "pointer" }}>
              <input
                type="file"
                multiple
                style={{ display: "none" }}
                onChange={(e) => {
                  attach(e.target.files);
                  e.target.value = "";
                }}
              />
              <span className="attach-link">{uploading ? "Attaching…" : "📎 Attach"}</span>
            </label>
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
          <button
            className="primary"
            onClick={send}
            disabled={busy || uploading || (!body.trim() && pending.length === 0)}
          >
            {asQuery ? "Send & request action" : "Send"}
          </button>
        </div>
      </div>
    </div>
  );
}
