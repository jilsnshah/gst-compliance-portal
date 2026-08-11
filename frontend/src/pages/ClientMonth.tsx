import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { download, get, upload } from "../api";
import type { CaseSummary, ReturnItem } from "../api";
import Discussion from "../components/Discussion";
import { Bar, dateTime, money, shortDate } from "../components/ui";

/* The client's entire month: six ordered steps, one line of plain English
   each, at most one button. No tabs, no status vocabulary. */

type StepState = "done" | "yours" | "with_ca" | "locked";

interface Step {
  key: string;
  title: string;
  state: StepState;
  line: string;
  item?: ReturnItem;
}

const DOT: Record<StepState, string> = {
  done: "✓",
  yours: "▶",
  with_ca: "•",
  locked: "·",
};

const TONE: Record<StepState, string> = {
  done: "green",
  yours: "amber",
  with_ca: "blue",
  locked: "grey",
};

const STATE_LABEL: Record<StepState, string> = {
  done: "Done",
  yours: "Your turn",
  with_ca: "With your CA team",
  locked: "Not yet",
};

export default function ClientMonth() {
  const { caseId } = useParams();
  const [data, setData] = useState<(CaseSummary & { documents: any[] }) | null>(null);
  const [workings, setWorkings] = useState<any>(null);
  const [recon, setRecon] = useState<any>(null);
  const [openStep, setOpenStep] = useState<string | null>(null);
  const [error, setError] = useState("");

  const reload = useCallback(() => {
    get(`/api/cases/${caseId}`).then(setData).catch((e) => setError(e.message));
    get(`/api/cases/${caseId}/gstr3b`).then(setWorkings).catch(() => {});
    get(`/api/cases/${caseId}/recon/reports`).then(setRecon).catch(() => {});
  }, [caseId]);

  useEffect(reload, [reload]);

  if (error) return <div className="error">{error}</div>;
  if (!data) return <div className="empty">Loading…</div>;

  const by = Object.fromEntries(data.returns.map((r) => [r.return_type, r])) as Record<string, ReturnItem>;
  const g1 = by.GSTR1;
  const pr = by.PR_RECON;
  const b3 = by.GSTR3B;

  const ack = (returnType: string) => {
    const item = by[returnType];
    const doc = data.documents.find(
      (d: any) => d.doc_type === "ACKNOWLEDGEMENT" && d.return_item_id === item?.id,
    );
    return doc?.versions?.length ? doc.versions[doc.versions.length - 1] : null;
  };

  const stateOf = (item: ReturnItem): StepState =>
    item.client_status === "DONE" ? "done" : item.client_status === "ACTION_NEEDED" ? "yours" : "with_ca";

  const g1Filed = g1.client_status === "DONE";
  const g1Ack = ack("GSTR1");
  const b3Ack = ack("GSTR3B");
  const paid = workings?.payment_status === "PAYMENT_CONFIRMED";
  const attention = recon?.summary?.action_required ?? 0;

  const steps: Step[] = [
    {
      key: "sales",
      title: "Sales data for GSTR-1",
      item: g1,
      state: g1.client_status === "DONE" ? "done" : g1.status === "ACTION_NEEDED" ? "yours" : stateOf(g1),
      line:
        g1.client_status === "DONE"
          ? "Verified and filed."
          : g1.client_status === "ACTION_NEEDED"
            ? g1.has_open_query
              ? "Your CA team has asked you something below."
              : "Upload your sales data for this month."
            : "Your CA team is checking your sales data.",
    },
    {
      key: "gstr1-filed",
      title: "GSTR-1 filed",
      state: g1Filed ? "done" : "locked",
      line: g1Filed
        ? g1Ack
          ? "Filed. Your acknowledgement receipt is ready."
          : "Filed on the GST portal. Receipt will appear here shortly."
        : "Happens once your sales data is verified.",
    },
    {
      key: "purchase",
      title: "Purchase register",
      item: pr,
      state: !g1Filed && pr.client_status !== "DONE" && pr.progress === 0 ? "locked" : stateOf(pr),
      line: !g1Filed && pr.progress === 0
        ? "Unlocks once GSTR-1 is filed."
        : pr.client_status === "DONE"
          ? "Reconciled against GSTR-2B."
          : pr.client_status === "ACTION_NEEDED"
            ? pr.has_open_query
              ? "Your CA team has asked you something below."
              : "Upload your purchase register for this month."
            : "Your CA team is matching your purchases against GSTR-2B.",
    },
    {
      key: "matching",
      title: "Purchase matching",
      item: pr,
      state: pr.client_status === "DONE" ? "done" : recon?.summary ? (attention > 0 ? "yours" : "with_ca") : "locked",
      line: !recon?.summary
        ? "Runs once both files are in."
        : pr.client_status === "DONE"
          ? `${recon.summary.match_rate}% matched, everything resolved.`
          : attention > 0
            ? `${attention} invoice${attention === 1 ? "" : "s"} need looking at.`
            : "Everything matched — your CA team is finalising.",
    },
    {
      key: "payment",
      title: "Tax payment",
      item: b3,
      // A challan existing is what says tax is due; none by the time the
      // return is signed off means nothing was payable.
      state: paid
        ? "done"
        : workings?.challan
          ? "yours"
          : b3?.blocked_reason
            ? "locked"
            : b3?.client_status === "DONE" || b3?.status === "VERIFIED"
              ? "done"
              : "with_ca",
      line: paid
        ? "Payment confirmed."
        : workings?.challan
          ? "Download the challan, pay it on the GST portal, then confirm here."
          : b3?.blocked_reason
            ? "Comes after the purchase matching is finished."
            : b3?.client_status === "DONE" || b3?.status === "VERIFIED"
              ? "Nothing was payable this month."
              : "Your CA team is checking whether anything is payable.",
    },
    {
      key: "gstr3b-filed",
      title: "GSTR-3B filed",
      state: b3.client_status === "DONE" ? "done" : b3?.blocked_reason ? "locked" : "with_ca",
      line:
        b3.client_status === "DONE"
          ? b3Ack
            ? "Filed. Your acknowledgement receipt is ready."
            : "Filed on the GST portal. Receipt will appear here shortly."
          : b3?.blocked_reason
            ? "The last step of the month."
            : "Your CA team will file this on the GST portal.",
    },
  ];

  const done = steps.filter((s) => s.state === "done").length;
  const yours = steps.filter((s) => s.state === "yours").length;

  return (
    <>
      <div className="page-head">
        <div>
          <h1>
            {data.period.label} · {data.entity.trade_name ?? data.entity.legal_name}
          </h1>
          <div className="sub">
            <span className="mono">{data.gstin}</span> · GSTR-3B due {shortDate(data.period.gstr3b_due_date)}
          </div>
        </div>
        <div style={{ textAlign: "right" }}>
          <div style={{ fontSize: 22, fontWeight: 650 }}>
            {done} of {steps.length}
          </div>
          <div className="sub">{yours > 0 ? `${yours} waiting on you` : "nothing waiting on you"}</div>
        </div>
      </div>

      <Bar value={Math.round((100 * done) / steps.length)} />

      <div style={{ marginTop: 18 }}>
        {steps.map((step, i) => (
          <div key={step.key} className={`step ${step.state} ${openStep === step.key ? "open" : ""}`}>
            <button className="step-head" onClick={() => setOpenStep(openStep === step.key ? null : step.key)}>
              <span className={`step-dot ${TONE[step.state]}`}>{DOT[step.state]}</span>
              <span className="step-no">{i + 1}</span>
              <span className="step-title">
                <strong>{step.title}</strong>
                <span className="sub">{step.line}</span>
              </span>
              <span className={`pill ${TONE[step.state] === "grey" ? "" : TONE[step.state]}`}>
                {STATE_LABEL[step.state]}
              </span>
            </button>

            {openStep === step.key && (
              <div className="step-body">
                <StepBody
                  step={step}
                  data={data}
                  workings={workings}
                  recon={recon}
                  ack={step.key === "gstr1-filed" ? g1Ack : step.key === "gstr3b-filed" ? b3Ack : null}
                  reload={reload}
                />
              </div>
            )}
          </div>
        ))}
      </div>
    </>
  );
}

function StepBody({
  step,
  data,
  workings,
  recon,
  ack,
  reload,
}: {
  step: Step;
  data: any;
  workings: any;
  recon: any;
  ack: any;
  reload: () => void;
}) {
  if (step.key === "sales" || step.key === "purchase") {
    const docType = step.key === "sales" ? "GSTR1_DATA" : "PURCHASE_REGISTER";
    return (
      <>
        <ClientUpload caseId={data.id} docType={docType} item={step.item!} reload={reload} />
        <FileHistory documents={data.documents} docType={docType} />
        <h3 style={{ marginTop: 18 }}>Messages</h3>
        <Discussion returnItemId={step.item!.id} onChange={reload} />
      </>
    );
  }

  if (step.key === "gstr1-filed" || step.key === "gstr3b-filed") {
    if (!ack) return <div className="empty">{step.line}</div>;
    return (
      <div className="row between">
        <div>
          <strong>{ack.original_filename}</strong>
          <div className="sub">Filed acknowledgement from the GST portal</div>
        </div>
        <button
          className="primary"
          onClick={() => download(`/api/documents/versions/${ack.id}/download`, ack.original_filename)}
        >
          Download receipt
        </button>
      </div>
    );
  }

  if (step.key === "matching") {
    if (!recon?.summary) return <div className="empty">{step.line}</div>;
    return (
      <>
        <MatchingReport recon={recon} caseId={data.id} period={data.period.code} />
        <h3 style={{ marginTop: 18 }}>Messages</h3>
        <Discussion returnItemId={step.item!.id} onChange={reload} />
      </>
    );
  }

  if (step.key === "payment") {
    return <PaymentStep workings={workings} item={step.item!} reload={reload} />;
  }
  return null;
}

const PLAIN_MISMATCH: Record<string, string> = {
  EXACT_MATCH: "Matches exactly",
  MISSING_IN_2B: "Your supplier has not reported this invoice yet",
  MISSING_IN_PR: "Reported by a supplier but not in your books",
  MISMATCH: "The amounts do not agree",
  PARTIAL_MATCH: "The invoice date does not agree",
  PROBABLE_MATCH: "Probably the same invoice, some details differ",
};

/* The full reconciliation, not just the problems -- the client can see every
   category and download the same workbook the CA team works from. */
const REPORT_TABS: { key: string; label: string; blurb: string }[] = [
  { key: "matched", label: "Matched", blurb: "These agree with the GST portal. Nothing to do." },
  {
    key: "missing_in_gstr2b",
    label: "Not reported by supplier",
    blurb: "In your books, but your supplier has not filed them yet. You cannot claim credit until they do.",
  },
  {
    key: "missing_in_purchase_register",
    label: "Not in your books",
    blurb: "A supplier reported these to the GST portal, but they are not in your purchase register.",
  },
  { key: "mismatch", label: "Amounts differ", blurb: "The same invoice, but the values do not agree." },
  { key: "partial_match", label: "Dates differ", blurb: "The same invoice and amounts, but a different date." },
  {
    key: "probable_match",
    label: "Probably the same",
    blurb: "Likely the same invoice with a different number or supplier GSTIN.",
  },
];

function MatchingReport({
  recon,
  caseId,
  period,
}: {
  recon: any;
  caseId: number;
  period: string;
}) {
  const [tab, setTab] = useState("matched");
  const counts: Record<string, number> = Object.fromEntries(
    REPORT_TABS.map((t) => [t.key, recon.reports[t.key]?.length ?? 0]),
  );
  const active = REPORT_TABS.find((t) => t.key === tab)!;
  const rows = recon.reports[tab] ?? [];

  return (
    <>
      <div className="row between" style={{ marginBottom: 14 }}>
        <div className="row" style={{ gap: 22 }}>
          <span>
            <strong style={{ fontSize: 20 }}>{recon.summary.match_rate}%</strong>
            <span className="sub"> matched</span>
          </span>
          <span>
            <strong style={{ fontSize: 20 }}>{recon.summary.action_required}</strong>
            <span className="sub"> need attention</span>
          </span>
          <span>
            <strong style={{ fontSize: 20 }}>{recon.summary.total}</strong>
            <span className="sub"> invoices compared</span>
          </span>
        </div>
        <button
          onClick={() =>
            download(`/api/cases/${caseId}/recon/export`, `purchase_matching_${period}.xlsx`)
          }
        >
          Download full report
        </button>
      </div>

      <div className="tabs">
        {REPORT_TABS.map((t) => (
          <button key={t.key} className={tab === t.key ? "active" : ""} onClick={() => setTab(t.key)}>
            {t.label} ({counts[t.key]})
          </button>
        ))}
      </div>

      <p className="sub" style={{ marginTop: 0 }}>
        {active.blurb}
      </p>

      {rows.length === 0 ? (
        <div className="empty">Nothing in this category.</div>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Supplier</th>
              <th>Invoice</th>
              <th>Date</th>
              <th className="num">Your books</th>
              <th className="num">GST portal</th>
              <th className="num">Difference</th>
              <th>What it means</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((m: any) => {
              const ref = m.purchase_register ?? m.gstr2b;
              return (
                <tr key={m.id}>
                  <td>
                    {ref?.supplier_name ?? "—"}
                    <div className="sub mono">{ref?.supplier_gstin}</div>
                  </td>
                  <td className="mono">{ref?.invoice_no}</td>
                  <td className="sub">{shortDate(ref?.invoice_date)}</td>
                  <td className="num">
                    {m.purchase_register ? money(m.purchase_register.taxable_value) : "—"}
                  </td>
                  <td className="num">{m.gstr2b ? money(m.gstr2b.taxable_value) : "—"}</td>
                  <td className="num" style={{ color: m.taxable_value_diff ? "var(--red)" : undefined }}>
                    {m.taxable_value_diff ? money(m.taxable_value_diff) : "—"}
                  </td>
                  <td className="sub">
                    {PLAIN_MISMATCH[m.match_status] ?? m.match_status}
                    {m.client_response && (
                      <div className="sub" style={{ marginTop: 2 }}>
                        You said: {m.client_response}
                      </div>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </>
  );
}

function ClientUpload({
  caseId,
  docType,
  item,
  reload,
}: {
  caseId: number;
  docType: string;
  item: ReturnItem;
  reload: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  if (item.client_status === "DONE") return null;

  return (
    <div className="upload-box">
      {err && <div className="error">{err}</div>}
      <div className="row">
        <input type="file" style={{ flex: 1 }} onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        <button
          className="primary"
          disabled={!file || busy}
          onClick={async () => {
            if (!file) return;
            setBusy(true);
            setErr("");
            try {
              const form = new FormData();
              form.append("doc_type", docType);
              form.append("file", file);
              form.append("return_item_id", String(item.id));
              await upload(`/api/cases/${caseId}/documents`, form);
              setFile(null);
              reload();
            } catch (e: any) {
              setErr(e.message);
            } finally {
              setBusy(false);
            }
          }}
        >
          {busy ? "Uploading…" : "Upload file"}
        </button>
      </div>
      <div className="sub" style={{ marginTop: 8 }}>
        Uploading again replaces nothing — your CA team sees every version.
      </div>
    </div>
  );
}

function FileHistory({ documents, docType }: { documents: any[]; docType: string }) {
  const doc = documents.find((d: any) => d.doc_type === docType);
  if (!doc?.versions?.length) return null;
  return (
    <table style={{ marginTop: 12 }}>
      <tbody>
        {[...doc.versions].reverse().map((v: any, i: number) => (
          <tr key={v.id}>
            <td>
              {v.original_filename}
              {i === 0 && (
                <span className="pill green" style={{ marginLeft: 8 }}>
                  Latest
                </span>
              )}
            </td>
            <td className="sub">
              {v.uploaded_on_behalf_of_client ? "uploaded by your CA team for you" : `by ${v.uploaded_by_name}`}
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
  );
}

function PaymentStep({
  workings,
  item,
  reload,
}: {
  workings: any;
  item: ReturnItem;
  reload: () => void;
}) {
  const [reference, setReference] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  if (!workings) return <div className="empty">Loading…</div>;
  if (!workings.challan)
    return <div className="empty">No challan has been sent to you for this month.</div>;

  return (
    <>
      {err && <div className="error">{err}</div>}
      <div className="row between">
        <div>
          <strong>{workings.challan.filename}</strong>
          <div className="sub">
            Sent by your CA team · {dateTime(workings.challan.uploaded_at)}
          </div>
        </div>
        <button
          className="primary"
          onClick={() => download(workings.challan.download_url, workings.challan.filename)}
        >
          Download challan
        </button>
      </div>

      {workings.payment ? (
        <div className="banner blue" style={{ marginTop: 14 }}>
          <div>
            <strong>Payment confirmed</strong>
            <div className="sub">
              {dateTime(workings.payment.confirmed_at)}
              {workings.payment.reference && ` · ref ${workings.payment.reference}`}
            </div>
          </div>
        </div>
      ) : (
        <div className="upload-box" style={{ marginTop: 14 }}>
          <h3>Once you have paid it on the GST portal</h3>
          <div className="row">
            <input
              placeholder="Payment reference (optional)"
              value={reference}
              onChange={(e) => setReference(e.target.value)}
            />
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
                  reload();
                } catch (e: any) {
                  setErr(e.message);
                } finally {
                  setBusy(false);
                }
              }}
            >
              {busy ? "Saving…" : "I have paid"}
            </button>
          </div>
          <div className="sub" style={{ marginTop: 6 }}>
            A receipt or screenshot helps your CA team, but is not required.
          </div>
        </div>
      )}
    </>
  );
}
