import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { get, post } from "../api";
import { Bar, Card, Pill, humanise, shortDate } from "../components/ui";

/* A file's whole year at once. The CA looks a file up, sees every month's
   state side by side, and only then picks the month to work in -- rather than
   having to know which month they wanted before they can look at anything. */

const ORDER = ["GSTR1", "PR_RECON", "GSTR3B"] as const;
const SHORT: Record<string, string> = { GSTR1: "GSTR-1", PR_RECON: "Recon", GSTR3B: "GSTR-3B" };

const TONE: Record<string, string> = {
  FILED: "green",
  VERIFIED: "blue",
  UNDER_CA_REVIEW: "blue",
  CLIENT_DATA_SUBMITTED: "blue",
  AWAITING_PAYMENT: "amber",
  AWAITING_CLIENT_DATA: "amber",
};

const MONTHS = Array.from({ length: 12 }, (_, i) =>
  new Date(2000, i, 1).toLocaleString("en", { month: "short" }),
);

export default function FileProfile() {
  const { entityId } = useParams();
  const [data, setData] = useState<any>(null);
  const [year, setYear] = useState<number | "">("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const load = () => {
    get(`/api/entities/${entityId}${year ? `?year=${year}` : ""}`)
      .then((d) => {
        setData(d);
        if (year === "" && d.years?.length) setYear(d.years[0]);
      })
      .catch((e) => setErr(e.message));
  };
  useEffect(load, [entityId, year]);

  if (err) return <div className="error">{err}</div>;
  if (!data) return <div className="empty">Loading…</div>;

  const shownYear = year || new Date().getFullYear();
  const byMonth: Record<number, any> = {};
  data.months.forEach((m: any) => {
    if (m.period.year === shownYear) byMonth[m.period.month] = m;
  });

  async function openMonth(month: number) {
    setBusy(true);
    setErr("");
    try {
      await post("/api/cases", { entity_id: Number(entityId), year: shownYear, month });
      load();
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>{data.legal_name}</h1>
          <div className="sub">
            {data.client_name} · file {data.file_number} · <span className="mono">{data.gstin}</span> ·
            PAN <span className="mono">{data.pan}</span> · {humanise(data.constitution)} ·{" "}
            {humanise(data.filing_frequency)}
          </div>
        </div>
        <div className="row">
          <select
            style={{ width: 130 }}
            value={shownYear}
            onChange={(e) => setYear(Number(e.target.value))}
          >
            {Array.from(new Set([...(data.years ?? []), new Date().getFullYear(), shownYear]))
              .sort((a, b) => b - a)
              .map((y) => (
                <option key={y} value={y}>
                  {y}
                </option>
              ))}
          </select>
          <Link to="/ca/clients">
            <button className="ghost">← All files</button>
          </Link>
        </div>
      </div>

      {err && <div className="error">{err}</div>}

      <Card title={`${shownYear} — month by month`}>
        <div className="grid cols-3">
          {MONTHS.map((label, i) => {
            const month = i + 1;
            const m = byMonth[month];
            return (
              <div key={month} className="upload-box">
                <div className="row between">
                  <strong>
                    {label} {shownYear}
                  </strong>
                  {m ? <Pill value={m.status} label={humanise(m.status)} /> : <span className="sub">not opened</span>}
                </div>

                {m ? (
                  <>
                    <div style={{ margin: "10px 0 6px" }}>
                      <Bar value={m.progress} />
                    </div>
                    <table>
                      <tbody>
                        {ORDER.map((rt) => {
                          const r = m.returns.find((x: any) => x.return_type === rt);
                          if (!r) return null;
                          return (
                            <tr key={rt}>
                              <td style={{ padding: "3px 0" }}>{SHORT[rt]}</td>
                              <td style={{ padding: "3px 0" }}>
                                <span className={`dot ${TONE[r.status] ?? "grey"}`} />{" "}
                                <span className="sub">{humanise(r.status)}</span>
                              </td>
                              <td className="num sub" style={{ padding: "3px 0" }}>
                                {r.waiting_on === "CLIENT"
                                  ? "client"
                                  : r.waiting_on === "CA"
                                    ? "us"
                                    : "—"}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                    <Link to={`/cases/${m.case_id}`}>
                      <button className="primary" style={{ width: "100%", marginTop: 10 }}>
                        Open {label}
                      </button>
                    </Link>
                  </>
                ) : (
                  <button
                    style={{ width: "100%", marginTop: 10 }}
                    disabled={busy}
                    onClick={() => openMonth(month)}
                  >
                    Open this month
                  </button>
                )}
              </div>
            );
          })}
        </div>
      </Card>

      <Card title="File details">
        <table>
          <tbody>
            <tr>
              <td className="sub">Trade name</td>
              <td>{data.trade_name ?? "—"}</td>
            </tr>
            <tr>
              <td className="sub">State</td>
              <td>{data.state_name ?? data.address?.state ?? "—"}</td>
            </tr>
            <tr>
              <td className="sub">Registered</td>
              <td>{shortDate(data.registration_date)}</td>
            </tr>
            <tr>
              <td className="sub">Contact</td>
              <td>
                {data.contact_person ?? "—"}
                {data.contact_email && ` · ${data.contact_email}`}
                {data.contact_phone && ` · ${data.contact_phone}`}
              </td>
            </tr>
            <tr>
              <td className="sub">Services</td>
              <td>{(data.applicable_services ?? []).join(", ") || "—"}</td>
            </tr>
          </tbody>
        </table>
      </Card>
    </>
  );
}
