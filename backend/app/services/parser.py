from __future__ import annotations

import io
import re
from datetime import date, datetime
from typing import Optional

from openpyxl import load_workbook

from app.core.enums import InvoiceSource

# Canonical field -> header aliases. Client purchase registers and GST portal
# 2B exports never agree on wording, so mapping is config, not code.
COLUMN_ALIASES = {
    "supplier_gstin": [
        "gstin", "gstin of supplier", "supplier gstin", "gstin/uin of recipient",
        "supplier gstin/uin", "gstin of the supplier", "party gstin", "vendor gstin",
    ],
    "supplier_name": [
        "trade/legal name", "supplier name", "trade name", "legal name",
        "party name", "vendor name", "name of supplier",
    ],
    "invoice_no": [
        "invoice number", "invoice no", "invoice no.", "inv no", "bill no",
        "document number", "doc no", "invoice/document no", "bill number",
    ],
    "invoice_date": [
        "invoice date", "inv date", "bill date", "document date", "doc date", "date",
    ],
    "invoice_type": ["invoice type", "document type", "type", "nature of supply"],
    "place_of_supply": ["place of supply", "pos", "state"],
    "taxable_value": [
        "taxable value", "taxable value (rs)", "taxable amount", "assessable value",
        "basic amount", "net amount", "taxable val",
    ],
    "igst": ["integrated tax", "igst", "igst amount", "integrated tax(rs)", "igst (rs)"],
    "cgst": ["central tax", "cgst", "cgst amount", "central tax(rs)", "cgst (rs)"],
    "sgst": [
        "state/ut tax", "state tax", "sgst", "sgst amount", "sgst/utgst",
        "state/ut tax(rs)", "sgst (rs)",
    ],
    "cess": ["cess", "cess amount", "cess(rs)"],
    "total_value": [
        "invoice value", "total value", "total amount", "invoice value (rs)",
        "gross total", "bill amount",
    ],
    "itc_available": ["itc availability", "itc available", "availability of itc"],
}

NUMERIC_FIELDS = ["taxable_value", "igst", "cgst", "sgst", "cess", "total_value"]
REQUIRED_FIELDS = ["supplier_gstin", "invoice_no", "invoice_date", "taxable_value"]

_HEADER_LOOKUP = {}
for field, aliases in COLUMN_ALIASES.items():
    for alias in aliases:
        _HEADER_LOOKUP[alias] = field


def _norm_header(value) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower()
    text = re.sub(r"[\n\r]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" :*")


def normalize_invoice_no(value) -> str:
    """Join key: upper-cased, punctuation removed, leading zeros dropped.
    'INV-0012/26' and 'inv 12/26' collapse to the same key."""
    if value is None:
        return ""
    text = re.sub(r"[^A-Za-z0-9]", "", str(value)).upper()
    stripped = text.lstrip("0")
    return stripped or text


def parse_date(value) -> Optional[date]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%d-%b-%Y", "%d %b %Y", "%m/%d/%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def parse_number(value) -> float:
    if value is None or value == "":
        return 0.0
    if isinstance(value, (int, float)):
        return round(float(value), 2)
    text = re.sub(r"[,\s₹]", "", str(value))
    if text in ("", "-"):
        return 0.0
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()")
    try:
        num = float(text)
    except ValueError:
        return 0.0
    return round(-num if negative else num, 2)


def _find_header_row(rows, max_scan: int = 15):
    """GST portal exports carry preamble rows, so the header is located by
    scoring each candidate row against the alias table."""
    best_index, best_map, best_score = None, {}, 0
    for idx, row in enumerate(rows[:max_scan]):
        mapping, score = {}, 0
        for col_idx, cell in enumerate(row):
            field = _HEADER_LOOKUP.get(_norm_header(cell))
            if field and field not in mapping:
                mapping[field] = col_idx
                score += 1
        if score > best_score:
            best_index, best_map, best_score = idx, mapping, score
    return best_index, best_map, best_score


def parse_invoice_workbook(data: bytes, source: InvoiceSource) -> dict:
    """Returns {'records': [...], 'errors': [...], 'header_row': int,
    'mapped_columns': {...}, 'unmapped_headers': [...]}"""
    workbook = load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    sheet = workbook[workbook.sheetnames[0]]
    rows = [list(r) for r in sheet.iter_rows(values_only=True)]
    workbook.close()

    if not rows:
        return {"records": [], "errors": ["Workbook is empty"], "header_row": None,
                "mapped_columns": {}, "unmapped_headers": []}

    header_index, mapping, score = _find_header_row(rows)
    if header_index is None or score < 3:
        return {
            "records": [],
            "errors": [
                "Could not identify a header row. Expected columns such as "
                "GSTIN, Invoice Number, Invoice Date, Taxable Value."
            ],
            "header_row": None,
            "mapped_columns": {},
            "unmapped_headers": [],
        }

    header_row = rows[header_index]
    unmapped = [
        str(c) for i, c in enumerate(header_row)
        if c and i not in mapping.values() and _norm_header(c)
    ]

    records, errors = [], []
    missing = [f for f in REQUIRED_FIELDS if f not in mapping]
    if missing:
        errors.append("Missing required columns: " + ", ".join(missing))

    for offset, row in enumerate(rows[header_index + 1:], start=header_index + 2):
        if all(cell is None or str(cell).strip() == "" for cell in row):
            continue

        def cell(field):
            idx = mapping.get(field)
            return row[idx] if idx is not None and idx < len(row) else None

        rec = {
            "source_row_no": offset,
            "supplier_gstin": (str(cell("supplier_gstin")).strip().upper()
                               if cell("supplier_gstin") else None),
            "supplier_name": str(cell("supplier_name")).strip() if cell("supplier_name") else None,
            "invoice_no": str(cell("invoice_no")).strip() if cell("invoice_no") else None,
            "invoice_date": parse_date(cell("invoice_date")),
            "invoice_type": str(cell("invoice_type")).strip() if cell("invoice_type") else None,
            "place_of_supply": (str(cell("place_of_supply")).strip()
                                if cell("place_of_supply") else None),
            "itc_available": (str(cell("itc_available")).strip()[:5]
                              if cell("itc_available") else None),
        }
        for field in NUMERIC_FIELDS:
            rec[field] = parse_number(cell(field))

        rec["invoice_no_normalized"] = normalize_invoice_no(rec["invoice_no"])

        if not rec["total_value"]:
            rec["total_value"] = round(
                rec["taxable_value"] + rec["igst"] + rec["cgst"] + rec["sgst"] + rec["cess"], 2
            )

        row_errors = []
        if not rec["invoice_no"]:
            row_errors.append("missing invoice number")
        if not rec["supplier_gstin"]:
            row_errors.append("missing supplier GSTIN")
        if rec["invoice_date"] is None:
            row_errors.append("unreadable invoice date")
        if row_errors:
            errors.append(f"Row {offset}: " + "; ".join(row_errors))
            if not rec["invoice_no"]:
                continue

        rec["raw"] = {
            _norm_header(header_row[i]): (str(row[i]) if row[i] is not None else None)
            for i in range(min(len(header_row), len(row)))
            if header_row[i] is not None
        }
        records.append(rec)

    return {
        "records": records,
        "errors": errors,
        "header_row": header_index + 1,
        "mapped_columns": {k: v for k, v in mapping.items()},
        "unmapped_headers": unmapped,
        "source": source.value,
    }
