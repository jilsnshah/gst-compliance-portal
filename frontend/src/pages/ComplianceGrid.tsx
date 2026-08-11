import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { get } from "../api";
import { Card, humanise } from "../components/ui";

const TONE: Record<string, string> = {
  FILED: "green",
  VERIFIED: "blue",
  UNDER_CA_REVIEW: "blue",
  CLIENT_DATA_SUBMITTED: "blue",
  AWAITING_PAYMENT: "amber",
  AWAITING_CLIENT_DATA: "amber",
};

const ORDER = ["GSTR1", "PR_RECON", "GSTR3B"] as const;

export default function ComplianceGrid() {
  const [data, setData] = useState<any>(null);
  const [year, setYear] = useState("");

  useEffect(() => {
    get(`/api/dashboard/grid${year ? `?year=${year}` : ""}`).then(setData);
  }, [year]);

  if (!data) return <div className="empty">Loading…</div>;

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Compliance grid</h1>
          <div className="sub">
            One row per GSTIN, one column per month. Three dots per cell: GSTR-1, reconciliation, GSTR-3B.
          </div>
        </div>
        <input placeholder="Year" style={{ width: 120 }} value={year} onChange={(e) => setYear(e.target.value)} />
      </div>

      <Card>
        <table>
          <thead>
            <tr>
              <th>Client / GSTIN</th>
              {data.periods.map((p: any) => (
                <th key={p.code} className="num">
                  {p.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.rows.map((row: any) => (
              <tr key={row.gstin}>
                <td>
                  <strong>{row.client}</strong>
                  <div className="sub">
                    {row.entity} · <span className="mono">{row.gstin}</span>
                  </div>
                </td>
                {data.periods.map((p: any) => {
                  const cell = row.cells[p.code];
                  if (!cell)
                    return (
                      <td key={p.code} className="sub num">
                        —
                      </td>
                    );
                  return (
                    <td key={p.code} className="num">
                      <Link to={`/cases/${cell.case_id}`} title={ORDER.map((rt) => `${rt}: ${humanise(cell.returns[rt])}`).join("\n")}>
                        <span className="cell" style={{ justifyContent: "flex-end" }}>
                          {ORDER.map((rt) => (
                            <span key={rt} className={`dot ${TONE[cell.returns[rt]] ?? "grey"}`} />
                          ))}
                        </span>
                      </Link>
                    </td>
                  );
                })}
              </tr>
            ))}
            {data.rows.length === 0 && (
              <tr>
                <td colSpan={99} className="empty">
                  No compliance months opened yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
        <div className="row sub" style={{ marginTop: 14 }}>
          <span className="dot green" /> filed
          <span className="dot blue" /> in progress
          <span className="dot amber" /> waiting on client
          <span className="dot grey" /> not applicable
        </div>
      </Card>
    </>
  );
}
