from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.serializers import audit_out, case_out, client_out
from app.core.db import get_db
from app.core.enums import (
    MatchStatus,
    MismatchResolution,
    QueryStatus,
    ReturnStatus,
    ReturnType,
    Role,
    is_terminal,
)
from app.models import (
    AuditLog,
    Client,
    ComplianceCase,
    Conversation,
    Document,
    Entity,
    GSTRegistration,
    InvoiceMatch,
    Message,
    Query,
    ReconciliationRun,
    ReturnItem,
    TaxPeriod,
    User,
)
from app.services.permissions import require_ca, visible_client_ids
from app.services.workflow import WORK_BUCKETS

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _scope(db: Session, user: User, stmt, column):
    ids = visible_client_ids(db, user)
    if ids is None:
        return stmt
    return stmt.where(column.in_(ids or [-1]))


@router.get("/client")
def client_dashboard(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    year: Optional[int] = None,
    month: Optional[int] = None,
    entity_id: Optional[int] = None,
    limit: int = 12,
):
    """The simple view: one card per open month with progress and what the
    client still has to do."""
    stmt = select(ComplianceCase).join(TaxPeriod, TaxPeriod.id == ComplianceCase.tax_period_id)
    stmt = _scope(db, user, stmt, ComplianceCase.client_id)
    if year:
        stmt = stmt.where(TaxPeriod.year == year)
    if month:
        stmt = stmt.where(TaxPeriod.month == month)
    if entity_id:
        stmt = stmt.where(ComplianceCase.entity_id == entity_id)
    stmt = stmt.order_by(TaxPeriod.year.desc(), TaxPeriod.month.desc()).limit(limit)
    cases = db.execute(stmt).scalars().all()

    cards = []
    for case in cases:
        out = case_out(db, case, user)
        returns = out["returns"]
        out["overall_progress"] = (
            int(sum(r["progress"] for r in returns) / len(returns)) if returns else 0
        )
        out["documents"] = db.execute(
            select(func.count(Document.id)).where(Document.case_id == case.id)
        ).scalar_one()
        out["open_queries"] = db.execute(
            select(func.count(Query.id)).where(
                Query.case_id == case.id, Query.status == QueryStatus.OPEN
            )
        ).scalar_one()
        out["action_required"] = [
            r["return_label"] for r in returns if r["client_status"] == "ACTION_NEEDED"
        ]

        run = db.execute(
            select(ReconciliationRun)
            .where(ReconciliationRun.case_id == case.id, ReconciliationRun.is_superseded.is_(False))
            .order_by(ReconciliationRun.id.desc())
            .limit(1)
        ).scalars().first()
        out["reconciliation"] = (
            {
                "match_rate": (run.summary or {}).get("match_rate", 0),
                "action_required": (run.summary or {}).get("action_required", 0),
                "total": (run.summary or {}).get("total", 0),
            }
            if run
            else None
        )
        cards.append(out)

    clients_stmt = _scope(db, user, select(Client), Client.id)
    entities_stmt = _scope(db, user, select(Entity), Entity.client_id)
    unread = db.execute(
        select(func.count(Message.id))
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(Message.is_internal_note.is_(False), Message.author_user_id != user.id)
    ).scalar_one()

    return {
        "clients": [client_out(c) for c in db.execute(clients_stmt).scalars().all()],
        "entities": [
            {
                "id": e.id,
                "legal_name": e.legal_name,
                "trade_name": e.trade_name,
                "file_number": e.file_number,
                "client_id": e.client_id,
                "gstins": [
                    {"id": r.id, "gstin": r.gstin, "state_name": r.state_name}
                    for r in e.registrations
                ],
            }
            for e in db.execute(entities_stmt).scalars().all()
        ],
        "cases": cards,
        "message_count": unread,
    }


@router.get("/ca")
def ca_dashboard(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    year: Optional[int] = None,
    month: Optional[int] = None,
    employee_id: Optional[int] = None,
    client_id: Optional[int] = None,
):
    """Today's work: counts per return type per bucket, plus the queues that
    actually need a person to act."""
    require_ca(user)

    stmt = (
        select(ReturnItem)
        .join(ComplianceCase, ComplianceCase.id == ReturnItem.case_id)
        .join(TaxPeriod, TaxPeriod.id == ComplianceCase.tax_period_id)
    )
    stmt = _scope(db, user, stmt, ComplianceCase.client_id)
    if year:
        stmt = stmt.where(TaxPeriod.year == year)
    if month:
        stmt = stmt.where(TaxPeriod.month == month)
    if employee_id:
        stmt = stmt.where(ReturnItem.assigned_employee_id == employee_id)
    if client_id:
        stmt = stmt.where(ComplianceCase.client_id == client_id)
    items = db.execute(stmt).scalars().all()

    status_to_bucket = {}
    for bucket, statuses in WORK_BUCKETS.items():
        for s in statuses:
            status_to_bucket[s] = bucket

    # "waiting_on_client" is not a stored state: it is UNDER_CA_REVIEW with an
    # unanswered query sitting with the client.
    blocked = set(
        db.execute(
            select(Query.return_item_id).where(Query.status == QueryStatus.OPEN)
        ).scalars()
    )

    buckets = list(WORK_BUCKETS) + ["waiting_on_client"]
    work = {rt.value: {b: 0 for b in buckets} for rt in ReturnType}
    for item in items:
        rt = item.return_type if isinstance(item.return_type, str) else item.return_type.value
        bucket = status_to_bucket[ReturnStatus(item.status)]
        if bucket == "to_review" and item.id in blocked:
            bucket = "waiting_on_client"
        work[rt][bucket] += 1

    today = date.today()
    overdue = [
        i
        for i in items
        if i.due_date and i.due_date < today and not is_terminal(i.return_type, i.status)
    ]

    open_queries = db.execute(
        _scope(
            db,
            user,
            select(func.count(Query.id)).join(
                ComplianceCase, ComplianceCase.id == Query.case_id
            ).where(Query.status != QueryStatus.RESOLVED),
            ComplianceCase.client_id,
        )
    ).scalar_one()

    unresolved_mismatches = db.execute(
        _scope(
            db,
            user,
            select(func.count(InvoiceMatch.id))
            .join(ComplianceCase, ComplianceCase.id == InvoiceMatch.case_id)
            .join(ReconciliationRun, ReconciliationRun.id == InvoiceMatch.run_id)
            .where(
                ReconciliationRun.is_superseded.is_(False),
                InvoiceMatch.match_status != MatchStatus.EXACT_MATCH,
                InvoiceMatch.resolution_status.notin_(
                    [MismatchResolution.RESOLVED, MismatchResolution.WRITTEN_OFF]
                ),
            ),
            ComplianceCase.client_id,
        )
    ).scalar_one()

    return {
        "work": work,
        "totals": {
            "return_items": len(items),
            "overdue": len(overdue),
            "open_queries": open_queries,
            "unresolved_mismatches": unresolved_mismatches,
        },
        "overdue_items": [
            {
                "return_item_id": i.id,
                "case_id": i.case_id,
                "return_type": i.return_type if isinstance(i.return_type, str) else i.return_type.value,
                "status": ReturnStatus(i.status).value,
                "due_date": i.due_date,
                "assigned_employee_id": i.assigned_employee_id,
            }
            for i in sorted(overdue, key=lambda x: x.due_date)[:50]
        ],
    }


@router.get("/grid")
def compliance_grid(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    year: Optional[int] = None,
):
    """Rows = GSTINs, columns = months, cells = per-return status. The single
    view a CA firm actually runs the month from."""
    require_ca(user)
    stmt = (
        select(ComplianceCase)
        .join(TaxPeriod, TaxPeriod.id == ComplianceCase.tax_period_id)
        .order_by(TaxPeriod.year, TaxPeriod.month)
    )
    stmt = _scope(db, user, stmt, ComplianceCase.client_id)
    if year:
        stmt = stmt.where(TaxPeriod.year == year)
    cases = db.execute(stmt).scalars().all()

    rows = {}
    periods = {}
    for case in cases:
        period = db.get(TaxPeriod, case.tax_period_id)
        reg = db.get(GSTRegistration, case.gst_registration_id)
        entity = db.get(Entity, case.entity_id)
        client = db.get(Client, case.client_id)
        periods[period.code] = {"code": period.code, "label": period.label}
        row = rows.setdefault(
            reg.gstin,
            {
                "gstin": reg.gstin,
                "gst_registration_id": reg.id,
                "entity": entity.legal_name,
                "client": client.name,
                "cells": {},
            },
        )
        row["cells"][period.code] = {
            "case_id": case.id,
            "case_status": case.status if isinstance(case.status, str) else case.status.value,
            "returns": {
                (i.return_type if isinstance(i.return_type, str) else i.return_type.value): ReturnStatus(
                    i.status
                ).value
                for i in case.return_items
            },
        }

    return {
        "periods": sorted(periods.values(), key=lambda p: p["code"]),
        "rows": sorted(rows.values(), key=lambda r: (r["client"], r["gstin"])),
    }


@router.get("/audit")
def firm_audit(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    limit: int = 100,
    client_id: Optional[int] = None,
):
    require_ca(user)
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
    ids = visible_client_ids(db, user)
    if ids is not None:
        stmt = stmt.where(AuditLog.client_id.in_(ids or [-1]))
    if client_id:
        stmt = stmt.where(AuditLog.client_id == client_id)
    return [audit_out(log) for log in db.execute(stmt).scalars().all()]
