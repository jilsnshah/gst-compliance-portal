import { Fragment, useCallback, useEffect, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { download, get, isCA, patch, post, upload } from "../api";
import type { CaseSummary, ReturnItem } from "../api";
import { useAuth } from "../auth";
import ColumnMapper from "../components/ColumnMapper";
import Discussion from "../components/Discussion";
import { Bar, Card, Pill, dateTime, humanise, money, shortDate } from "../components/ui";

type Tab = "overview" | "GSTR1" | "PR_RECON" | "GSTR3B" | "documents" | "audit";

const DOC_LABEL: Record<string, string> = {
  GSTR1_DATA: "GSTR-1 sales data",
  GSTR3B_DATA: "GSTR-3B data",
  PURCHASE_REGISTER: "Purchase Register",
  GSTR2B: "GSTR-2B",
  CHALLAN: "Challan",
  PAYMENT_PROOF: "Payment proof",
  ACKNOWLEDGEMENT: "Acknowledgement",
  SUPPORTING: "Supporting document",
};

export default function CaseWorkspace() {
  const { caseId } = useParams();
  const { user } = useAuth();
  const ca = isCA(user?.role);
  // Tab lives in the URL so the inbox can deep-link straight to the stage.
  const [params, setParams] = useSearchParams();
  const tab = (params.get("tab") as Tab) ?? "overview";
  const setTab = (next: Tab) => setParams(next === "overview" ? {} : { tab: next }, { replace: true });
  const [data, setData] = useState<(CaseSummary & { documents: any[] }) | null>(null);
  const [error, setError] = useState("");

  const reload = useCallback(() => {
    get(`/api/cases/${caseId}`)
      .then(setData)
      .catch((e) => setError(e.message));
  }, [caseId]);

  useEffect(reload, [reload]);

  if (error) return <div className="error">{error}</div>;
  if (!data) return <div className="empty">Loading…</div>;

  const byType = Object.fromEntries(data.returns.map((r) => [r.return_type, r])) as Record<string, ReturnItem>;
  const overall = Math.round(data.returns.reduce((n, r) => n + r.progress, 0) / data.returns.length);

  return (
    <>
      <div className="page-head">
        <div>
          <h1>
            {data.period.label} · {data.entity.trade_name ?? data.entity.legal_name}
          </h1>
          <div className="sub">
            {data.client.name} · <span className="mono">{data.gstin}</span> · file {data.entity.file_number}
          </div>
        </div>
        <Pill value={data.status} />
      </div>

      <div className="tabs">
        {(
          [
            ["overview", "Overview"],
            ["GSTR1", "GSTR-1"],
            ["PR_RECON", "GSTR-2B Reconciliation"],
            ["GSTR3B", "GSTR-3B & Payment"],
            ["documents", "Documents"],
            ...(ca ? ([["audit", "Audit trail"]] as const) : []),
          ] as [Tab, string][]
        ).map(([key, label]) => (
          <button key={key} className={tab === key ? "active" : ""} onClick={() => setTab(key)}>
            {label}
          </button>
        ))}
      </div>

      {tab === "overview" && <Overview data={data} overall={overall} onOpen={setTab} />}
      {tab === "GSTR1" && (
        <ReturnTrack item={byType.GSTR1} caseData={data} docType="GSTR1_DATA" reload={reload} />
      )}
      {tab === "PR_RECON" && <Reconciliation item={byType.PR_RECON} caseData={data} reload={reload} />}
      {tab === "GSTR3B" && <Gstr3b item={byType.GSTR3B} caseData={data} reload={reload} />}
      {tab === "documents" && <Documents data={data} />}
      {tab === "audit" && <CaseAudit caseId={data.id} />}
    </>
  );
}

/* ------------------------------------------------------------ overview */
function Overview({ data, overall, onOpen }: { data: any; overall: number; onOpen: (t: Tab) => void }) {
  const { user } = useAuth();
  const ca = isCA(user?.role);
  return (
    <>
      <Card title="Month status">
        <div className="row between" style={{ fontSize: 12, color: "var(--muted)" }}>
          <span>Overall progress</span>
          <span>{overall}%</span>
        </div>
        <Bar value={overall} />
        <table style={{ marginTop: 16 }}>
          <thead>
            <tr>
              <th>Track</th>
              <th>Status</th>
              <th>Progress</th>
              <th>Due</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {data.returns.map((r: ReturnItem) => (
              <tr key={r.id}>
                <td>
                  <strong>{r.return_label}</strong>
                </td>
                <td>
                  <Pill value={ca ? r.status : r.client_status} label={ca ? humanise(r.status) : r.client_status_label} />
                </td>
                <td style={{ minWidth: 120 }}>
                  <Bar value={r.progress} />
                </td>
                <td className="sub">{shortDate(r.due_date)}</td>
                <td className="num">
                  <button className="ghost" onClick={() => onOpen(r.return_type as Tab)}>
                    Open →
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <Card title="Registration">
        <table>
          <tbody>
            <tr>
              <td className="sub">Client</td>
              <td>{data.client.name}</td>
            </tr>
            <tr>
              <td className="sub">File / entity</td>
              <td>
                {data.entity.legal_name} ({data.entity.file_number})
              </td>
            </tr>
            <tr>
              <td className="sub">GSTIN</td>
              <td className="mono">{data.gstin}</td>
            </tr>
            <tr>
              <td className="sub">Tax period</td>
              <td>{data.period.label}</td>
            </tr>
            <tr>
              <td className="sub">GSTR-1 due</td>
              <td>{shortDate(data.period.gstr1_due_date)}</td>
            </tr>
            <tr>
              <td className="sub">GSTR-3B due</td>
              <td>{shortDate(data.period.gstr3b_due_date)}</td>
            </tr>
          </tbody>
        </table>
      </Card>
    </>
  );
}

/* -------------------------------------------------- generic return track */
/* The workflow engine speaks in states; the CA thinks in actions. This table
   is the translation. Anything not named here stays reachable under
   "Other transitions" so the engine never gets a dead end. */
interface StageAction {
  to: string;
  label: string;
  primary?: boolean;
}

interface StageMeta {
  ca: string;
  actions?: StageAction[];
}

// Clients never see internal CA states, so their wording keys off the
// simplified status the API already sends them.
const CLIENT_META: Record<string, string> = {
  ACTION_NEEDED: "Something needs you — upload the file above, or reply in the discussion below.",
  WITH_CA: "Your CA team is working on this.",
  DONE: "Completed for this month.",
};

const STAGE_META: Record<string, StageMeta> = {
  AWAITING_CLIENT_DATA: {
    ca: "Waiting for the client to upload. You can upload on their behalf above.",
  },
  CLIENT_DATA_SUBMITTED: {
    ca: "The client has uploaded. Nobody has checked it yet.",
    actions: [
      { to: "UNDER_CA_REVIEW", label: "Start review", primary: true },
      { to: "AWAITING_CLIENT_DATA", label: "Ask for a different file" },
    ],
  },
  UNDER_CA_REVIEW: {
    ca: "You are checking the data. Queries and re-uploads happen below without changing this status.",
    actions: [{ to: "VERIFIED", label: "Data is correct", primary: true }],
  },
  AWAITING_PAYMENT: {
    ca: "Challan is with the client. Confirm the payment once it lands.",
    actions: [{ to: "UNDER_CA_REVIEW", label: "Withdraw challan" }],
  },
  VERIFIED: {
    ca: "Signed off. File it on the GST portal, then record the ARN below.",
    actions: [{ to: "UNDER_CA_REVIEW", label: "Reopen review" }],
  },
  FILED: {
    ca: "Filed. Upload the acknowledgement below so the client can download it.",
    actions: [{ to: "UNDER_CA_REVIEW", label: "Reopen (admin)" }],
  },
};

// The reconciliation track finishes at VERIFIED -- nothing is filed for it.
const RECON_OVERRIDES: Record<string, Partial<StageMeta>> = {
  AWAITING_CLIENT_DATA: {
    ca: "Upload GSTR-2B above; waiting for the client's purchase register.",
  },
  UNDER_CA_REVIEW: {
    ca: "Run the matching above and clear the invoices that need attention.",
    actions: [{ to: "VERIFIED", label: "Reconciliation complete", primary: true }],
  },
  VERIFIED: {
    ca: "Reconciliation finalised. GSTR-3B is now unblocked.",
    actions: [{ to: "UNDER_CA_REVIEW", label: "Reopen" }],
  },
};

const GSTR3B_OVERRIDES: Record<string, Partial<StageMeta>> = {
  AWAITING_CLIENT_DATA: {
    ca: "Waiting for the client's GSTR-3B figures. You can upload them on their behalf below.",
  },
  UNDER_CA_REVIEW: {
    ca: "Check the client's figures against the GST portal. Upload the challan below if tax is payable.",
    actions: [{ to: "VERIFIED", label: "Nothing payable — sign off", primary: true }],
  },
  AWAITING_PAYMENT: {
    ca: "Challan is with the client. Their confirmation clears this for filing.",
    actions: [{ to: "UNDER_CA_REVIEW", label: "Withdraw challan" }],
  },
};

function stageMeta(item: ReturnItem): StageMeta {
  const key = item.internal_status ?? item.status;
  const base = STAGE_META[key] ?? { ca: "" };
  const overrides =
    item.return_type === "PR_RECON"
      ? RECON_OVERRIDES
      : item.return_type === "GSTR3B"
        ? GSTR3B_OVERRIDES
        : null;
  return overrides?.[key] ? { ...base, ...overrides[key] } : base;
}

function StageStatus({ item, reload }: { item: ReturnItem; reload: () => void }) {
  const { user } = useAuth();
  const ca = isCA(user?.role);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const meta = stageMeta(item);
  const named = (meta.actions ?? []).filter((a) => item.allowed_next.includes(a.to));
  // FILED and AWAITING_PAYMENT have their own forms (they need an ARN / a
  // challan), so they must never appear as a plain status button.
  const unnamed = item.allowed_next.filter(
    (s) => !named.some((a) => a.to === s) && s !== "FILED" && s !== "AWAITING_PAYMENT",
  );

  async function move(to: string, label: string) {
    setBusy(true);
    setErr("");
    try {
      await post(`/api/return-items/${item.id}/transition`, { to_status: to, note: label });
      reload();
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  const explain = item.blocked_reason
    ? item.blocked_reason
    : ca
      ? meta.ca
      : CLIENT_META[item.client_status] ?? "";
  const files = ca && item.return_type !== "PR_RECON";
  const showFilingForm = files && item.status === "VERIFIED";
  const showFiled = files && item.status === "FILED";
  if (!explain && !showFilingForm && !showFiled && (!ca || named.length === 0)) return null;

  const reviewer =
    ca && item.review_started_by && item.status === "UNDER_CA_REVIEW" ? (
      <div className="sub" style={{ marginBottom: 10 }}>
        Picked up by <strong>{item.review_started_by}</strong> · {dateTime(item.review_started_at)}
      </div>
    ) : null;

  return (
    <div className="upload-box" style={{ marginTop: 12 }}>
      {err && <div className="error">{err}</div>}
      {explain && <div style={{ marginBottom: reviewer ? 6 : named.length || unnamed.length ? 10 : 0 }}>{explain}</div>}
      {reviewer}
      {ca && named.length > 0 && (
        <div className="row">
          {named.map((a) => (
            <button key={a.to} className={a.primary ? "primary" : ""} disabled={busy} onClick={() => move(a.to, a.label)}>
              {a.label}
            </button>
          ))}
        </div>
      )}
      {showFilingForm && <RecordFilingForm item={item} reload={reload} />}
      {showFiled && <FiledSummary item={item} reload={reload} />}
      {ca && unnamed.length > 0 && (
        <details style={{ marginTop: 10 }}>
          <summary>Other transitions</summary>
          <div className="row" style={{ marginTop: 8 }}>
            {unnamed.map((s) => (
              <button key={s} disabled={busy} onClick={() => move(s, humanise(s))}>
                {humanise(s)}
              </button>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}

function UploadBox({
  caseId,
  docType,
  returnItemId,
  reload,
  allowOnBehalf,
}: {
  caseId: number;
  docType: string;
  returnItemId?: number;
  reload: () => void;
  allowOnBehalf?: boolean;
}) {
  const { user } = useAuth();
  const ca = isCA(user?.role);
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [report, setReport] = useState<any>(null);

  async function send() {
    if (!file) return;
    setBusy(true);
    setErr("");
    setReport(null);
    try {
      const form = new FormData();
      form.append("doc_type", docType);
      form.append("file", file);
      if (returnItemId) form.append("return_item_id", String(returnItemId));
      const res = await upload(`/api/cases/${caseId}/documents`, form);
      setReport(res.parse_report);
      setFile(null);
      reload();
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="upload-box">
      <h3>Upload {DOC_LABEL[docType] ?? docType}</h3>
      {err && <div className="error">{err}</div>}
      <div className="row">
        <input
          type="file"
          style={{ flex: 1 }}
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
        <button className="primary" onClick={send} disabled={!file || busy}>
          {busy ? "Uploading…" : "Upload new version"}
        </button>
      </div>
      {ca && allowOnBehalf && (
        <div className="sub" style={{ marginTop: 8 }}>
          Recorded as uploaded on the client's behalf, and moves the stage on just as their own
          upload would.
        </div>
      )}
      {report && (
        <div className="sub" style={{ marginTop: 10 }}>
          Parsed <strong>{report.records}</strong> invoice rows (header row {report.header_row}).
          {report.errors?.length > 0 && (
            <details style={{ marginTop: 6 }}>
              <summary>{report.errors.length} row warning(s)</summary>
              <ul>
                {report.errors.slice(0, 20).map((e: string, i: number) => (
                  <li key={i}>{e}</li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}
    </div>
  );
}

function LatestMapper({
  documents,
  docType,
  reload,
}: {
  documents: any[];
  docType: string;
  reload: () => void;
}) {
  const doc = documents.find((d: any) => d.doc_type === docType);
  const latest = doc?.versions?.length ? doc.versions[doc.versions.length - 1] : null;
  if (!latest) return null;
  return (
    <ColumnMapper versionId={latest.id} filename={latest.original_filename} onDone={reload} />
  );
}

function VersionList({ documents, docTypes }: { documents: any[]; docTypes: string[] }) {
  const docs = documents.filter((d) => docTypes.includes(d.doc_type));
  if (docs.length === 0) return <div className="empty">No files uploaded yet.</div>;
  return (
    <table>
      <thead>
        <tr>
          <th>Document</th>
          <th>Ver</th>
          <th>File</th>
          <th>Uploaded by</th>
          <th>When</th>
          <th>Status</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {docs.flatMap((d) =>
          [...d.versions].reverse().map((v: any) => (
            <tr key={v.id}>
              <td>{DOC_LABEL[d.doc_type] ?? d.doc_type}</td>
              <td>
                v{v.version_no}
                {v.version_no === d.current_version_no && (
                  <span className="pill green" style={{ marginLeft: 6 }}>
                    Latest
                  </span>
                )}
              </td>
              <td>{v.original_filename}</td>
              <td className="sub">{uploaderLabel(v)}</td>
              <td className="sub" style={{ whiteSpace: "nowrap" }}>{dateTime(v.created_at)}</td>
              <td>
                <Pill value={v.status} />
              </td>
              <td className="num">
                <button className="ghost" onClick={() => download(`/api/documents/versions/${v.id}/download`, v.original_filename)}>
                  Download
                </button>
              </td>
            </tr>
          )),
        )}
      </tbody>
    </table>
  );
}

/* Filing is one action: the ARN is what sets FILED, and the acknowledgement
   comes with it when the CA already has the PDF, or straight after when they
   do not. Neither is a bare status button. */
function RecordFilingForm({ item, reload }: { item: ReturnItem; reload: () => void }) {
  const [arn, setArn] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  async function submit() {
    setBusy(true);
    setErr("");
    try {
      await post(`/api/return-items/${item.id}/file`, { arn });
      if (file) {
        const form = new FormData();
        form.append("file", file);
        await upload(`/api/return-items/${item.id}/acknowledgement`, form);
      }
      setArn("");
      setFile(null);
      reload();
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ marginTop: 12 }}>
      {err && <div className="error">{err}</div>}
      <div className="row">
        <input placeholder="ARN from the GST portal" value={arn} onChange={(e) => setArn(e.target.value)} style={{ flex: 1 }} />
        <input type="file" style={{ flex: 1 }} onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        <button className="primary" disabled={busy || !arn} onClick={submit}>
          {busy ? "Recording…" : "Record filing"}
        </button>
      </div>
      <div className="sub" style={{ marginTop: 6 }}>
        Attach the acknowledgement now if you have it — otherwise record the ARN and upload the
        receipt when it arrives.
      </div>
    </div>
  );
}

function FiledSummary({ item, reload }: { item: ReturnItem; reload: () => void }) {
  const [filing, setFiling] = useState<any>(null);
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const load = () => {
    get(`/api/return-items/${item.id}/filing`).then(setFiling);
  };
  useEffect(load, [item.id, item.updated_at]);

  async function uploadAck() {
    if (!file) return;
    setBusy(true);
    setErr("");
    try {
      const form = new FormData();
      form.append("file", file);
      await upload(`/api/return-items/${item.id}/acknowledgement`, form);
      setFile(null);
      load();
      reload();
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  const ack = filing?.acknowledgement;
  return (
    <div style={{ marginTop: 12 }}>
      {err && <div className="error">{err}</div>}
      <div className="sub">
        ARN <span className="mono">{filing?.arn ?? "—"}</span> · filed {shortDate(filing?.filed_on)}
      </div>
      {ack ? (
        <div className="row between" style={{ marginTop: 8 }}>
          <span>
            Acknowledgement: <strong>{ack.original_filename}</strong>
          </span>
          <button onClick={() => download(`/api/documents/versions/${ack.id}/download`, ack.original_filename)}>
            Download
          </button>
        </div>
      ) : (
        <>
          <div className="banner amber" style={{ marginTop: 8 }}>
            <div>
              <strong>Acknowledgement still missing</strong>
              <div className="sub">The client cannot download a receipt until this is uploaded.</div>
            </div>
          </div>
          <div className="row">
            <input type="file" style={{ flex: 1 }} onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
            <button className="primary" disabled={!file || busy} onClick={uploadAck}>
              Upload receipt
            </button>
          </div>
        </>
      )}
    </div>
  );
}

function ReturnTrack({
  item,
  caseData,
  docType,
  reload,
}: {
  item: ReturnItem;
  caseData: any;
  docType: string;
  reload: () => void;
}) {
  const { user } = useAuth();
  const ca = isCA(user?.role);
  // Ordered: what to do now, then the file it concerns, then the conversation.
  // The client's data and the acknowledgement are different things and no
  // longer share an upload box.
  return (
    <>
      <Card
        title={item.return_label}
        actions={
          <Pill
            value={ca ? item.status : item.client_status}
            label={ca ? humanise(item.status) : item.client_status_label}
          />
        }
      >
        <Bar value={item.progress} />
        <div className="sub" style={{ marginTop: 8 }}>
          Due {shortDate(item.due_date)} · last updated {dateTime(item.updated_at)}
        </div>
        <StageStatus item={item} reload={reload} />
      </Card>

      <Card title="Client's data">
        <VersionList documents={caseData.documents} docTypes={[docType]} />
        {ca && <LatestMapper documents={caseData.documents} docType={docType} reload={reload} />}
        {!item.is_terminal && (
          <div style={{ marginTop: 12 }}>
            <UploadBox caseId={caseData.id} docType={docType} returnItemId={item.id} reload={reload} allowOnBehalf />
          </div>
        )}
      </Card>

      <Card title="Discussion with the client">
        <Discussion returnItemId={item.id} onChange={reload} />
      </Card>
    </>
  );
}

/* ------------------------------------------------------ reconciliation */
function Reconciliation({ item, caseData, reload }: { item: ReturnItem; caseData: any; reload: () => void }) {
  const { user } = useAuth();
  const ca = isCA(user?.role);
  const [status, setStatus] = useState<any>(null);
  const [reports, setReports] = useState<any>(null);
  const [bucket, setBucket] = useState("missing_in_gstr2b");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const load = () => {
    get(`/api/cases/${caseData.id}/recon`).then(setStatus);
    get(`/api/cases/${caseData.id}/recon/reports`).then(setReports);
  };
  useEffect(load, [caseData.id]);

  async function run() {
    setBusy(true);
    setErr("");
    try {
      await post(`/api/cases/${caseData.id}/recon/run`, { amount_tolerance: 1, date_tolerance_days: 15 });
      load();
      reload();
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  const summary = reports?.summary;
  const buckets = [
    ["matched", "Matched"],
    ["missing_in_gstr2b", "Missing in GSTR-2B"],
    ["missing_in_purchase_register", "Missing in Purchase Register"],
    ["mismatch", "Mismatch"],
    ["partial_match", "Partial match"],
    ["probable_match", "Probable match"],
  ] as const;

  return (
    <>
      <Card
        title="GSTR-2B ↔ Purchase Register"
        actions={<Pill value={ca ? item.status : item.client_status} label={ca ? humanise(item.status) : item.client_status_label} />}
      >
        {err && <div className="error">{err}</div>}
        <div className="grid cols-2">
          <div>
            <h3>GSTR-2B (uploaded by CA team)</h3>
            {status?.gstr2b_version ? (
              <>
                <div className="sub">
                  v{status.gstr2b_version.version_no} · {status.gstr2b_version.filename} ·{" "}
                  {status.gstr2b_version.rows} rows read
                </div>
                {ca && (
                  <ColumnMapper
                    versionId={status.gstr2b_version.id}
                    filename={status.gstr2b_version.filename}
                    onDone={load}
                  />
                )}
              </>
            ) : (
              <div className="sub">Not uploaded yet.</div>
            )}
            {ca && (
              <div style={{ marginTop: 10 }}>
                <UploadBox caseId={caseData.id} docType="GSTR2B" returnItemId={item.id} reload={load} />
              </div>
            )}
          </div>
          <div>
            <h3>Purchase Register (client)</h3>
            {status?.purchase_register_version ? (
              <>
                <div className="sub">
                  v{status.purchase_register_version.version_no} ·{" "}
                  {status.purchase_register_version.filename} ·{" "}
                  {status.purchase_register_version.rows} rows read
                </div>
                {ca && (
                  <ColumnMapper
                    versionId={status.purchase_register_version.id}
                    filename={status.purchase_register_version.filename}
                    onDone={load}
                  />
                )}
              </>
            ) : (
              <div className="sub">Not uploaded yet.</div>
            )}
            <div style={{ marginTop: 10 }}>
              <UploadBox
                caseId={caseData.id}
                docType="PURCHASE_REGISTER"
                returnItemId={item.id}
                reload={load}
                allowOnBehalf
              />
            </div>
          </div>
        </div>

        {ca && (
          <div className="row between" style={{ marginTop: 16 }}>
            <div className="sub">
              {status?.current_run?.stale && "A newer file was uploaded — re-run the reconciliation."}
            </div>
            <div className="row">
              {status?.current_run && (
                <button onClick={() => download(`/api/cases/${caseData.id}/recon/export`, `reconciliation_${caseData.period.code}.xlsx`)}>
                  Export to Excel
                </button>
              )}
              <button className="primary" onClick={run} disabled={!status?.ready_to_run || busy}>
                {busy ? "Running…" : status?.current_run ? "Re-run reconciliation" : "Run reconciliation"}
              </button>
            </div>
          </div>
        )}
        <StageStatus item={item} reload={reload} />
      </Card>

      {summary && (
        <>
          <div className="grid cols-3" style={{ marginBottom: 16 }}>
            <div className="stat">
              <div className="value">{summary.match_rate}%</div>
              <div className="label">Exact match rate</div>
            </div>
            <div className="stat">
              <div className="value">{summary.action_required}</div>
              <div className="label">Invoices needing attention</div>
            </div>
            <div className="stat">
              <div className="value">{summary.total}</div>
              <div className="label">Total lines compared</div>
            </div>
          </div>

          <Card title="Reconciliation reports">
            <div className="tabs">
              {buckets.map(([key, label]) => (
                <button key={key} className={bucket === key ? "active" : ""} onClick={() => setBucket(key)}>
                  {label} ({reports.reports[key]?.length ?? 0})
                </button>
              ))}
            </div>
            <MatchTable rows={reports.reports[bucket] ?? []} reload={load} />
          </Card>
        </>
      )}

      <Card title="Discussion with the client">
        <Discussion returnItemId={item.id} onChange={reload} />
      </Card>
    </>
  );
}

function MatchTable({ rows, reload }: { rows: any[]; reload: () => void }) {
  const { user } = useAuth();
  const ca = isCA(user?.role);
  const [open, setOpen] = useState<number | null>(null);

  if (rows.length === 0) return <div className="empty">Nothing in this category.</div>;

  return (
    <table>
      <thead>
        <tr>
          <th>Supplier</th>
          <th>Invoice</th>
          <th>Date</th>
          <th className="num">PR taxable</th>
          <th className="num">2B taxable</th>
          <th className="num">Tax diff</th>
          <th>Flags</th>
          <th>Resolution</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {rows.map((m) => {
          const ref = m.purchase_register ?? m.gstr2b;
          return (
            <Fragment key={m.id}>
              <tr>
                <td>
                  {ref?.supplier_name ?? "—"}
                  <div className="sub mono">{ref?.supplier_gstin}</div>
                </td>
                <td className="mono">{ref?.invoice_no}</td>
                <td className="sub">{shortDate(ref?.invoice_date)}</td>
                <td className="num">{m.purchase_register ? money(m.purchase_register.taxable_value) : "—"}</td>
                <td className="num">{m.gstr2b ? money(m.gstr2b.taxable_value) : "—"}</td>
                <td className="num" style={{ color: m.tax_diff ? "var(--red)" : undefined }}>
                  {m.tax_diff ? money(m.tax_diff) : "—"}
                </td>
                <td className="sub">{(m.diff_flags ?? []).map((f: string) => humanise(f)).join(", ") || "—"}</td>
                <td>
                  <Pill value={m.resolution_status} />
                </td>
                <td className="num">
                  <button className="ghost" onClick={() => setOpen(open === m.id ? null : m.id)}>
                    {open === m.id ? "Close" : "Discuss"}
                  </button>
                </td>
              </tr>
              {open === m.id && (
                <tr>
                  <td colSpan={9} style={{ background: "#fafbfc" }}>
                    {ca && (
                      <div className="row" style={{ marginBottom: 10 }}>
                        <span className="sub">Outcome for this invoice:</span>
                        <select
                          value={m.resolution_status}
                          onChange={async (e) => {
                            await patch(`/api/recon/matches/${m.id}`, { resolution_status: e.target.value });
                            reload();
                          }}
                          style={{ width: 220 }}
                        >
                          {["OPEN", "IN_PROGRESS", "CLIENT_RESPONDED", "RESOLVED", "DEFERRED_NEXT_PERIOD", "WRITTEN_OFF"].map((s) => (
                            <option key={s} value={s}>
                              {humanise(s)}
                            </option>
                          ))}
                        </select>
                        {m.resolution_note && <span className="sub">· {m.resolution_note}</span>}
                      </div>
                    )}
                    <Discussion matchId={m.id} compact onChange={reload} />
                  </td>
                </tr>
              )}
            </Fragment>
          );
        })}
      </tbody>
    </table>
  );
}

/* -------------------------------------------------------------- GSTR-3B */
function Gstr3b({ item, caseData, reload }: { item: ReturnItem; caseData: any; reload: () => void }) {
  const { user } = useAuth();
  const ca = isCA(user?.role);
  const [w, setW] = useState<any>(null);

  const load = () => {
    get(`/api/cases/${caseData.id}/gstr3b`).then(setW);
  };
  useEffect(load, [caseData.id, item.status]);

  if (!w) return <div className="empty">Loading…</div>;

  // No control sheet: the CA reads the figures on the GST portal. Uploading a
  // challan is how they say tax is payable; signing off is how they say it is not.
  return (
    <>
      <Card
        title="GSTR-3B"
        actions={
          <Pill
            value={ca ? item.status : item.client_status}
            label={ca ? humanise(item.status) : item.client_status_label}
          />
        }
      >
        <Bar value={item.progress} />
        <div className="sub" style={{ marginTop: 8 }}>
          Due {shortDate(item.due_date)} · last updated {dateTime(item.updated_at)}
        </div>
        <StageStatus item={item} reload={reload} />
      </Card>

      <Card title="Client's GSTR-3B data">
        <VersionList documents={caseData.documents} docTypes={["GSTR3B_DATA"]} />
        {ca && <LatestMapper documents={caseData.documents} docType="GSTR3B_DATA" reload={reload} />}
        {!item.is_terminal && (
          <div style={{ marginTop: 12 }}>
            <UploadBox
              caseId={caseData.id}
              docType="GSTR3B_DATA"
              returnItemId={item.id}
              reload={reload}
              allowOnBehalf
            />
          </div>
        )}
      </Card>

      <Card title="Tax payment">
        {w.challan ? (
          <div className="row between">
            <div>
              <strong>{w.challan.filename}</strong>
              <div className="sub">
                Sent to the client {dateTime(w.challan.uploaded_at)}
                {w.challan.note && ` · ${w.challan.note}`}
              </div>
            </div>
            <button onClick={() => download(w.challan.download_url, w.challan.filename)}>
              Download challan
            </button>
          </div>
        ) : (
          <div className="sub">
            No challan uploaded. Check the figures on the GST portal — upload the challan if tax is
            payable, or sign the return off above if nothing is due.
          </div>
        )}

        {w.payment && (
          <div className="banner blue" style={{ marginTop: 14 }}>
            <div>
              <strong>Payment confirmed</strong>
              <div className="sub">
                by {w.payment.confirmed_by} · {dateTime(w.payment.confirmed_at)}
                {w.payment.reference && ` · ref ${w.payment.reference}`}
              </div>
              {w.payment.note && <div className="sub">{w.payment.note}</div>}
            </div>
            {w.payment.proof && (
              <button onClick={() => download(w.payment.proof.download_url, w.payment.proof.filename)}>
                Payment proof
              </button>
            )}
          </div>
        )}

        {ca && !w.challan && item.status === "UNDER_CA_REVIEW" && !item.blocked_reason && (
          <ChallanUpload item={item} reload={reload} onDone={load} />
        )}
        {ca && item.status === "AWAITING_PAYMENT" && !w.payment && (
          <ConfirmPaymentForm item={item} reload={reload} onDone={load} forClient />
        )}
      </Card>

      <Card title="Discussion with the client">
        <Discussion returnItemId={item.id} onChange={reload} />
      </Card>
    </>
  );
}

function ChallanUpload({
  item,
  reload,
  onDone,
}: {
  item: ReturnItem;
  reload: () => void;
  onDone: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  return (
    <div className="upload-box" style={{ marginTop: 14 }}>
      <h3>Upload the challan from the GST portal</h3>
      {err && <div className="error">{err}</div>}
      <div className="row">
        <input type="file" style={{ flex: 1 }} onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        <input placeholder="Note for the client (optional)" value={note} onChange={(e) => setNote(e.target.value)} />
        <button
          className="primary"
          disabled={!file || busy}
          onClick={async () => {
            if (!file) return;
            setBusy(true);
            setErr("");
            try {
              const form = new FormData();
              form.append("file", file);
              if (note) form.append("note", note);
              await upload(`/api/return-items/${item.id}/challan`, form);
              setFile(null);
              setNote("");
              onDone();
              reload();
            } catch (e: any) {
              setErr(e.message);
            } finally {
              setBusy(false);
            }
          }}
        >
          {busy ? "Uploading…" : "Send challan to client"}
        </button>
      </div>
      <div className="sub" style={{ marginTop: 6 }}>
        Uploading it asks the client to pay — nothing from the challan is re-keyed here.
      </div>
    </div>
  );
}

function ConfirmPaymentForm({
  item,
  reload,
  onDone,
  forClient,
}: {
  item: ReturnItem;
  reload: () => void;
  onDone: () => void;
  forClient?: boolean;
}) {
  const [reference, setReference] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  return (
    <div className="upload-box" style={{ marginTop: 14 }}>
      <h3>{forClient ? "Record the payment for the client" : "Once you have paid on the GST portal"}</h3>
      {err && <div className="error">{err}</div>}
      <div className="row">
        <input placeholder="Reference (optional)" value={reference} onChange={(e) => setReference(e.target.value)} />
        <input type="file" style={{ flex: 1 }} onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        <button
          className="primary"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            setErr("");
            try {
              const form = new FormData();
              if (reference) form.append("reference", reference);
              if (file) form.append("file", file);
              await upload(`/api/return-items/${item.id}/payment-confirmation`, form);
              setReference("");
              setFile(null);
              onDone();
              reload();
            } catch (e: any) {
              setErr(e.message);
            } finally {
              setBusy(false);
            }
          }}
        >
          {busy ? "Saving…" : forClient ? "Mark as paid" : "I have paid"}
        </button>
      </div>
      <div className="sub" style={{ marginTop: 6 }}>
        Attach a payment screenshot or receipt if you have one — optional.
      </div>
    </div>
  );
}

/* ------------------------------------------------------------ documents */
/* The month's document set is fixed. Every slot is listed whether or not it
   has been uploaded, so both sides can see at a glance what the latest file is
   and what is still outstanding. */
const DOC_SLOTS: {
  docType: string;
  returnType: string;
  label: string;
  expectedFrom: string;
  optional?: boolean;
}[] = [
  { docType: "GSTR1_DATA", returnType: "GSTR1", label: "GSTR-1 sales data", expectedFrom: "Client" },
  { docType: "ACKNOWLEDGEMENT", returnType: "GSTR1", label: "GSTR-1 filing acknowledgement", expectedFrom: "CA team" },
  { docType: "GSTR2B", returnType: "PR_RECON", label: "GSTR-2B", expectedFrom: "CA team" },
  { docType: "GSTR3B_DATA", returnType: "GSTR3B", label: "GSTR-3B data", expectedFrom: "Client" },
  { docType: "PURCHASE_REGISTER", returnType: "PR_RECON", label: "Purchase Register", expectedFrom: "Client" },
  // Only needed when there is tax to pay.
  { docType: "CHALLAN", returnType: "GSTR3B", label: "GST challan", expectedFrom: "CA team", optional: true },
  { docType: "PAYMENT_PROOF", returnType: "GSTR3B", label: "Payment proof", expectedFrom: "Client", optional: true },
  { docType: "ACKNOWLEDGEMENT", returnType: "GSTR3B", label: "GSTR-3B filing acknowledgement", expectedFrom: "CA team" },
];

const uploaderLabel = (v: any) =>
  v.uploaded_on_behalf_of_client
    ? `${v.uploaded_by_name} (CA, on client's behalf)`
    : `${v.uploaded_by_name}${v.uploaded_by_role === "CLIENT" ? "" : " (CA team)"}`;

function Documents({ data }: { data: any }) {
  const returnItemId: Record<string, number> = Object.fromEntries(
    data.returns.map((r: ReturnItem) => [r.return_type, r.id]),
  );

  const slots = DOC_SLOTS.map((slot) => {
    const doc = data.documents.find(
      (d: any) => d.doc_type === slot.docType && d.return_item_id === returnItemId[slot.returnType],
    );
    const latest = doc?.versions?.length ? doc.versions[doc.versions.length - 1] : null;
    return { ...slot, doc, latest };
  });

  const slotDocIds = new Set(slots.filter((s) => s.doc).map((s) => s.doc.id));
  const others = data.documents.filter((d: any) => !slotDocIds.has(d.id) && d.versions?.length);
  const withHistory = [...slots.filter((s) => s.doc && s.latest).map((s) => ({ label: s.label, doc: s.doc })),
                       ...others.map((d: any) => ({ label: DOC_LABEL[d.doc_type] ?? d.doc_type, doc: d }))];
  const outstanding = slots.filter((s) => !s.latest && !s.optional).length;

  return (
    <>
      <Card
        title="Latest documents"
        actions={
          <span className="sub">
            {slots.filter((s) => s.latest).length} of {slots.length} uploaded
            {outstanding > 0 && ` · ${outstanding} still needed`}
          </span>
        }
      >
        <table>
          <thead>
            <tr>
              <th>Document</th>
              <th>Expected from</th>
              <th>Latest file</th>
              <th>Uploaded by</th>
              <th>When</th>
              <th>Status</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {slots.map((s) => (
              <tr key={`${s.returnType}-${s.docType}`} style={s.latest ? undefined : { opacity: 0.65 }}>
                <td>
                  <strong>{s.label}</strong>
                  {s.doc && s.doc.current_version_no > 1 && (
                    <div className="sub">{s.doc.current_version_no} versions</div>
                  )}
                </td>
                <td className="sub">{s.expectedFrom}</td>
                <td>
                  {s.latest ? (
                    <>
                      {s.latest.original_filename}
                      <span className="pill blue" style={{ marginLeft: 8 }}>
                        v{s.latest.version_no}
                      </span>
                    </>
                  ) : (
                    <span className="sub">Not uploaded yet</span>
                  )}
                </td>
                <td className="sub">{s.latest ? uploaderLabel(s.latest) : "—"}</td>
                <td className="sub" style={{ whiteSpace: "nowrap" }}>
                  {s.latest ? dateTime(s.latest.created_at) : "—"}
                </td>
                <td>
                  {!s.latest ? (
                    <Pill value="NOT_STARTED" label={s.optional ? "If needed" : "Pending"} />
                  ) : s.latest.status === "NOT_APPLICABLE" ? (
                    <span className="sub">—</span>
                  ) : (
                    <Pill value={s.latest.status} />
                  )}
                </td>
                <td className="num">
                  {s.latest && (
                    <button
                      className="primary"
                      onClick={() =>
                        download(`/api/documents/versions/${s.latest.id}/download`, s.latest.original_filename)
                      }
                    >
                      Download
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <Card title="Version history">
        {withHistory.length === 0 && <div className="empty">Nothing uploaded for this month yet.</div>}
        {withHistory.map(({ label, doc }) => (
          <div key={doc.id} style={{ marginBottom: 18 }}>
            <h3 style={{ marginBottom: 6 }}>{label}</h3>
            <table>
              <thead>
                <tr>
                  <th>Version</th>
                  <th>File</th>
                  <th>Uploaded by</th>
                  <th>When</th>
                  <th>Status</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {[...doc.versions].reverse().map((v: any, i: number) => (
                  <tr key={v.id}>
                    <td>
                      v{v.version_no}
                      {i === 0 && (
                        <span className="pill green" style={{ marginLeft: 6 }}>
                          Latest
                        </span>
                      )}
                    </td>
                    <td>{v.original_filename}</td>
                    <td className="sub">{uploaderLabel(v)}</td>
                    <td className="sub" style={{ whiteSpace: "nowrap" }}>
                      {dateTime(v.created_at)}
                    </td>
                    <td>
                      {v.status === "NOT_APPLICABLE" ? <span className="sub">—</span> : <Pill value={v.status} />}
                    </td>
                    <td className="num">
                      <button
                        className="ghost"
                        onClick={() => download(`/api/documents/versions/${v.id}/download`, v.original_filename)}
                      >
                        Download
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}
      </Card>
    </>
  );
}

function CaseAudit({ caseId }: { caseId: number }) {
  const [logs, setLogs] = useState<any[]>([]);
  useEffect(() => {
    get(`/api/cases/${caseId}/audit`).then(setLogs);
  }, [caseId]);
  return (
    <Card title="Audit trail">
      <table>
        <thead>
          <tr>
            <th>When</th>
            <th>Who</th>
            <th>Action</th>
            <th>Detail</th>
          </tr>
        </thead>
        <tbody>
          {logs.map((l) => (
            <tr key={l.id}>
              <td className="sub" style={{ whiteSpace: "nowrap" }}>{dateTime(l.created_at)}</td>
              <td>
                {l.actor_name}
                <div className="sub">{l.actor_role?.replace(/_/g, " ")}</div>
              </td>
              <td>
                <Pill value={l.action} />
              </td>
              <td>{l.description}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}
