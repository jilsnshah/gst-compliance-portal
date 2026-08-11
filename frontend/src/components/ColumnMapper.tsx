import { useEffect, useMemo, useState } from "react";
import { get, post } from "../api";

/* The CA states which column holds what, by position.

   Client workbooks arrive with arbitrary column names, in arbitrary order, and
   sometimes with no header row at all -- and the same client can send a
   different layout next month. So a saved mapping only ever pre-fills this
   panel; it is never applied behind the CA's back. */

const FIELD_LABELS: Record<string, string> = {
  supplier_gstin: "Supplier GSTIN",
  supplier_name: "Supplier name",
  invoice_no: "Invoice number",
  invoice_date: "Invoice date",
  invoice_type: "Invoice type",
  place_of_supply: "Place of supply",
  taxable_value: "Taxable value",
  igst: "IGST",
  cgst: "CGST",
  sgst: "SGST",
  cess: "Cess",
  total_value: "Invoice total",
  itc_available: "ITC available",
};

interface Sheet {
  name: string;
  columns: string[];
  rows: string[][];
  suggested_header_row: number | null;
}

export default function ColumnMapper({
  versionId,
  filename,
  onDone,
}: {
  versionId: number;
  filename: string;
  onDone?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<any>(null);
  const [sheetName, setSheetName] = useState("");
  const [headerRow, setHeaderRow] = useState<number | "">("");
  const [firstDataRow, setFirstDataRow] = useState(2);
  const [columns, setColumns] = useState<Record<string, number | "">>({});
  const [saveAs, setSaveAs] = useState("");
  const [result, setResult] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    if (!open || data) return;
    get(`/api/documents/versions/${versionId}/preview`)
      .then((d) => {
        setData(d);
        const first: Sheet = d.sheets[0];
        const saved = d.saved_mappings?.[0];
        if (saved) {
          // Pre-fill from what this client sent last time -- still editable.
          setSheetName(saved.sheet_name ?? first.name);
          setHeaderRow(saved.header_row ?? "");
          setFirstDataRow(saved.first_data_row ?? 2);
          setColumns(saved.columns ?? {});
          setSaveAs(saved.label ?? "");
        } else {
          setSheetName(first.name);
          setHeaderRow(first.suggested_header_row ?? "");
          setFirstDataRow((first.suggested_header_row ?? 0) + 1 || 1);
        }
      })
      .catch((e) => setErr(e.message));
  }, [open, versionId, data]);

  const sheet: Sheet | undefined = useMemo(
    () => data?.sheets?.find((s: Sheet) => s.name === sheetName) ?? data?.sheets?.[0],
    [data, sheetName],
  );

  // "A — GSTIN of supplier", or "E — (unnamed)" when the header cell is blank.
  const options = useMemo(() => {
    if (!sheet) return [];
    const header = headerRow ? sheet.rows[Number(headerRow) - 1] : undefined;
    return sheet.columns.map((letter, i) => {
      const name = header?.[i]?.trim();
      const sample = sheet.rows
        .slice(Math.max(Number(firstDataRow) - 1, 0))
        .map((r) => r[i])
        .find((v) => v && v.trim());
      return { index: i, letter, label: `${letter} — ${name || "(unnamed)"}`, sample };
    });
  }, [sheet, headerRow, firstDataRow]);

  async function apply() {
    setBusy(true);
    setErr("");
    setResult(null);
    try {
      const cols: Record<string, number> = {};
      Object.entries(columns).forEach(([f, i]) => {
        if (i !== "" && i !== undefined && i !== null) cols[f] = Number(i);
      });
      const res = await post(`/api/documents/versions/${versionId}/parse`, {
        mapping: {
          sheet_name: sheetName,
          header_row: headerRow === "" ? null : Number(headerRow),
          first_data_row: Number(firstDataRow),
          columns: cols,
        },
        save_as: saveAs || null,
      });
      setResult(res);
      onDone?.();
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <button className="ghost" style={{ paddingLeft: 0 }} onClick={() => setOpen(true)}>
        Set which column is which →
      </button>
    );
  }

  const required: string[] = data?.required ?? [];
  const missing = required.filter((f) => columns[f] === "" || columns[f] === undefined);

  return (
    <div className="upload-box" style={{ marginTop: 12 }}>
      <div className="row between">
        <h3 style={{ margin: 0 }}>Columns in {filename}</h3>
        <button className="ghost" onClick={() => setOpen(false)}>
          Close
        </button>
      </div>

      {err && <div className="error" style={{ marginTop: 8 }}>{err}</div>}
      {!data && <div className="empty">Reading the file…</div>}

      {data && sheet && (
        <>
          {data.saved_mappings?.length > 0 && (
            <div className="sub" style={{ margin: "8px 0" }}>
              Pre-filled from <strong>{data.saved_mappings[0].label}</strong>, saved for this client.
              Check it against the file below — the layout may have changed.
            </div>
          )}

          <div className="row" style={{ marginTop: 8 }}>
            {data.sheets.length > 1 && (
              <label className="sub">
                Sheet{" "}
                <select value={sheetName} onChange={(e) => setSheetName(e.target.value)} style={{ width: 180 }}>
                  {data.sheets.map((s: Sheet) => (
                    <option key={s.name} value={s.name}>
                      {s.name}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <label className="sub">
              Header row{" "}
              <input
                style={{ width: 90 }}
                placeholder="none"
                value={headerRow}
                onChange={(e) => setHeaderRow(e.target.value === "" ? "" : Number(e.target.value))}
              />
            </label>
            <label className="sub">
              Data starts at row{" "}
              <input
                style={{ width: 90 }}
                value={firstDataRow}
                onChange={(e) => setFirstDataRow(Number(e.target.value) || 1)}
              />
            </label>
          </div>

          <div style={{ overflowX: "auto", marginTop: 12 }}>
            <table className="mono" style={{ fontSize: 11.5 }}>
              <thead>
                <tr>
                  <th></th>
                  {sheet.columns.map((c) => (
                    <th key={c}>{c}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {sheet.rows.slice(0, 6).map((row, ri) => (
                  <tr
                    key={ri}
                    style={ri + 1 === Number(headerRow) ? { background: "var(--accent-soft)" } : undefined}
                  >
                    <td className="sub">{ri + 1}</td>
                    {sheet.columns.map((_, ci) => (
                      <td key={ci} style={{ whiteSpace: "nowrap", maxWidth: 150, overflow: "hidden" }}>
                        {row[ci]}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="grid cols-3" style={{ marginTop: 14 }}>
            {(data.fields ?? []).map((field: string) => (
              <label key={field} className="sub">
                {FIELD_LABELS[field] ?? field}
                {required.includes(field) && <span style={{ color: "var(--red)" }}> *</span>}
                <select
                  value={columns[field] ?? ""}
                  onChange={(e) =>
                    setColumns((c) => ({
                      ...c,
                      [field]: e.target.value === "" ? "" : Number(e.target.value),
                    }))
                  }
                >
                  <option value="">— not in this file —</option>
                  {options.map((o) => (
                    <option key={o.index} value={o.index}>
                      {o.label}
                    </option>
                  ))}
                </select>
                {columns[field] !== "" && columns[field] !== undefined && (
                  <span className="sub" style={{ fontSize: 11 }}>
                    e.g. {options[Number(columns[field])]?.sample ?? "—"}
                  </span>
                )}
              </label>
            ))}
          </div>

          <div className="row between" style={{ marginTop: 14 }}>
            <input
              placeholder="Remember this layout as… (e.g. Tally export)"
              value={saveAs}
              onChange={(e) => setSaveAs(e.target.value)}
              style={{ maxWidth: 320 }}
            />
            <button className="primary" onClick={apply} disabled={busy || missing.length > 0}>
              {busy ? "Reading…" : "Read the file with these columns"}
            </button>
          </div>
          {missing.length > 0 && (
            <div className="sub" style={{ marginTop: 6 }}>
              Still needed: {missing.map((f) => FIELD_LABELS[f] ?? f).join(", ")}
            </div>
          )}

          {result && (
            <div style={{ marginTop: 12 }}>
              <div className={result.records ? "banner blue" : "banner amber"}>
                <div>
                  <strong>{result.records} invoice rows read</strong>
                  {result.saved_mapping && (
                    <div className="sub">Layout saved as “{result.saved_mapping.label}”.</div>
                  )}
                </div>
              </div>
              {(result.warnings ?? []).map((w: string, i: number) => (
                <div key={i} className="error" style={{ marginTop: 6 }}>
                  {w}
                </div>
              ))}
              {(result.errors ?? []).length > 0 && (
                <details style={{ marginTop: 6 }}>
                  <summary>{result.errors.length} row issue(s)</summary>
                  <ul className="sub">
                    {result.errors.slice(0, 15).map((e: string, i: number) => (
                      <li key={i}>{e}</li>
                    ))}
                  </ul>
                </details>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
