from __future__ import annotations

from collections import defaultdict
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.enums import (
    AuditAction,
    DiffFlag,
    InvoiceSource,
    MatchStatus,
    MismatchResolution,
    NotificationType,
)
from app.models import (
    ComplianceCase,
    InvoiceMatch,
    InvoiceRecord,
    ReconciliationRun,
    ReturnItem,
    User,
)
from app.services import audit, notifications

DEFAULT_AMOUNT_TOLERANCE = 1.0  # rupees
DEFAULT_DATE_TOLERANCE_DAYS = 15


def _amount_flags(pr: InvoiceRecord, tb: InvoiceRecord, tol: float) -> list:
    flags = []
    pairs = [
        ("taxable_value", DiffFlag.TAXABLE_VALUE_MISMATCH),
        ("igst", DiffFlag.IGST_MISMATCH),
        ("cgst", DiffFlag.CGST_MISMATCH),
        ("sgst", DiffFlag.SGST_MISMATCH),
        ("cess", DiffFlag.CESS_MISMATCH),
    ]
    for field, flag in pairs:
        if abs((getattr(pr, field) or 0) - (getattr(tb, field) or 0)) > tol:
            flags.append(flag.value)
    if abs(pr.total_tax - tb.total_tax) > tol:
        flags.append(DiffFlag.TAX_AMOUNT_MISMATCH.value)
    return flags


def _build_match(
    case_id: int,
    run_id: int,
    pr: Optional[InvoiceRecord],
    tb: Optional[InvoiceRecord],
    status: MatchStatus,
    extra_flags: Optional[list] = None,
    tol: float = DEFAULT_AMOUNT_TOLERANCE,
    score: float = 0.0,
) -> InvoiceMatch:
    flags = list(extra_flags or [])
    taxable_diff = tax_diff = 0.0
    if pr and tb:
        flags += _amount_flags(pr, tb, tol)
        taxable_diff = round((pr.taxable_value or 0) - (tb.taxable_value or 0), 2)
        tax_diff = round(pr.total_tax - tb.total_tax, 2)
        # Key matched but the money did not -- that is a mismatch, not a match.
        if status in (MatchStatus.EXACT_MATCH, MatchStatus.PARTIAL_MATCH) and any(
            f for f in flags if f.endswith("_MISMATCH") and "INVOICE_DATE" not in f
        ):
            status = MatchStatus.MISMATCH
            score = min(score, 0.7)
    elif pr:
        taxable_diff = round(pr.taxable_value or 0, 2)
        tax_diff = round(pr.total_tax, 2)
    elif tb:
        taxable_diff = round(-(tb.taxable_value or 0), 2)
        tax_diff = round(-tb.total_tax, 2)

    return InvoiceMatch(
        case_id=case_id,
        run_id=run_id,
        pr_record_id=pr.id if pr else None,
        gstr2b_record_id=tb.id if tb else None,
        match_status=status,
        diff_flags=sorted(set(flags)),
        taxable_value_diff=taxable_diff,
        tax_diff=tax_diff,
        match_score=score,
        resolution_status=(
            MismatchResolution.RESOLVED
            if status == MatchStatus.EXACT_MATCH
            else MismatchResolution.OPEN
        ),
    )


def _index(records, keyfunc):
    buckets = defaultdict(list)
    for rec in records:
        buckets[keyfunc(rec)].append(rec)
    return buckets


def match_records(
    case_id: int,
    run_id: int,
    pr_records: list,
    tb_records: list,
    amount_tolerance: float = DEFAULT_AMOUNT_TOLERANCE,
    date_tolerance_days: int = DEFAULT_DATE_TOLERANCE_DAYS,
) -> list:
    """Deterministic multi-pass matcher. Each pass consumes the records it
    pairs, so later, looser passes only ever see genuine leftovers."""
    matches = []
    pr_left = list(pr_records)
    tb_left = list(tb_records)

    def consume(pass_keyfunc, status, flags, score, require=None):
        nonlocal pr_left, tb_left
        tb_index = _index(tb_left, pass_keyfunc)
        used_tb, remaining_pr = set(), []
        for pr in pr_left:
            candidates = [c for c in tb_index.get(pass_keyfunc(pr), []) if id(c) not in used_tb]
            if require:
                candidates = [c for c in candidates if require(pr, c)]
            if not candidates:
                remaining_pr.append(pr)
                continue
            tb = candidates[0]
            used_tb.add(id(tb))
            matches.append(
                _build_match(case_id, run_id, pr, tb, status, flags(pr, tb), amount_tolerance, score)
            )
        pr_left = remaining_pr
        tb_left = [t for t in tb_left if id(t) not in used_tb]

    # Pass 1 -- GSTIN + normalised invoice number + exact date.
    consume(
        lambda r: (r.supplier_gstin, r.invoice_no_normalized, r.invoice_date),
        MatchStatus.EXACT_MATCH,
        lambda pr, tb: [],
        1.0,
    )

    # Pass 2 -- same supplier and invoice number, date drifted.
    def date_within(pr, tb):
        if not pr.invoice_date or not tb.invoice_date:
            return True
        return abs((pr.invoice_date - tb.invoice_date).days) <= date_tolerance_days

    consume(
        lambda r: (r.supplier_gstin, r.invoice_no_normalized),
        MatchStatus.PARTIAL_MATCH,
        lambda pr, tb: [DiffFlag.INVOICE_DATE_MISMATCH.value],
        0.85,
        require=date_within,
    )

    # Pass 3 -- same supplier, date and taxable value; invoice number differs.
    consume(
        lambda r: (r.supplier_gstin, r.invoice_date, round(r.taxable_value or 0, 2)),
        MatchStatus.PROBABLE_MATCH,
        lambda pr, tb: [DiffFlag.INVOICE_NO_MISMATCH.value],
        0.65,
    )

    # Pass 4 -- same invoice, date and value; supplier GSTIN differs (typo or
    # wrong vendor selected in the purchase register).
    consume(
        lambda r: (r.invoice_no_normalized, r.invoice_date, round(r.taxable_value or 0, 2)),
        MatchStatus.PROBABLE_MATCH,
        lambda pr, tb: [DiffFlag.GSTIN_MISMATCH.value],
        0.6,
    )

    for pr in pr_left:
        matches.append(
            _build_match(case_id, run_id, pr, None, MatchStatus.MISSING_IN_2B, [], amount_tolerance)
        )
    for tb in tb_left:
        matches.append(
            _build_match(case_id, run_id, None, tb, MatchStatus.MISSING_IN_PR, [], amount_tolerance)
        )
    return matches


def summarise(matches: list) -> dict:
    summary = {"counts": {}, "taxable_value": {}, "tax": {}, "total": len(matches)}
    for status in MatchStatus:
        rows = [m for m in matches if m.match_status == status]
        summary["counts"][status.value] = len(rows)
        summary["taxable_value"][status.value] = round(
            sum(abs(m.taxable_value_diff) for m in rows), 2
        )
        summary["tax"][status.value] = round(sum(abs(m.tax_diff) for m in rows), 2)
    matched = summary["counts"][MatchStatus.EXACT_MATCH.value]
    summary["match_rate"] = round(100.0 * matched / len(matches), 1) if matches else 0.0
    summary["action_required"] = len(matches) - matched
    return summary


def run_reconciliation(
    db: Session,
    user: User,
    case: ComplianceCase,
    return_item: ReturnItem,
    pr_version_id: int,
    gstr2b_version_id: int,
    amount_tolerance: float = DEFAULT_AMOUNT_TOLERANCE,
    date_tolerance_days: int = DEFAULT_DATE_TOLERANCE_DAYS,
) -> ReconciliationRun:
    pr_records = db.execute(
        select(InvoiceRecord).where(
            InvoiceRecord.case_id == case.id,
            InvoiceRecord.source == InvoiceSource.PURCHASE_REGISTER,
            InvoiceRecord.document_version_id == pr_version_id,
        )
    ).scalars().all()
    tb_records = db.execute(
        select(InvoiceRecord).where(
            InvoiceRecord.case_id == case.id,
            InvoiceRecord.source == InvoiceSource.GSTR2B,
            InvoiceRecord.document_version_id == gstr2b_version_id,
        )
    ).scalars().all()

    db.execute(
        update(ReconciliationRun)
        .where(ReconciliationRun.case_id == case.id, ReconciliationRun.is_superseded.is_(False))
        .values(is_superseded=True)
    )

    run = ReconciliationRun(
        case_id=case.id,
        return_item_id=return_item.id,
        pr_version_id=pr_version_id,
        gstr2b_version_id=gstr2b_version_id,
        run_by_user_id=user.id,
        params={
            "amount_tolerance": amount_tolerance,
            "date_tolerance_days": date_tolerance_days,
            "pr_rows": len(pr_records),
            "gstr2b_rows": len(tb_records),
        },
    )
    db.add(run)
    db.flush()

    matches = match_records(
        case.id, run.id, pr_records, tb_records, amount_tolerance, date_tolerance_days
    )
    owner = return_item.assigned_employee_id
    for match in matches:
        match.assigned_employee_id = owner
        db.add(match)

    run.summary = summarise(matches)
    db.flush()

    audit.record(
        db,
        user,
        AuditAction.RECON_RUN,
        "ReconciliationRun",
        "Reconciliation run: {} PR rows vs {} GSTR-2B rows, {} require action".format(
            len(pr_records), len(tb_records), run.summary["action_required"]
        ),
        target_id=run.id,
        client_id=case.client_id,
        case_id=case.id,
        meta=run.summary,
    )
    notifications.notify(
        db,
        NotificationType.RECON_COMPLETED,
        title="Reconciliation completed",
        body="{} invoices require attention".format(run.summary["action_required"]),
        case=case,
        return_item=return_item,
        to_ca=True,
        to_client=True,
        exclude_user_id=user.id,
    )
    return run
