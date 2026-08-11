from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query as Q, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.serializers import audit_out, case_out, document_out, return_item_out
from app.core.db import get_db
from app.core.enums import AuditAction, CaseStatus, ReturnStatus, ReturnType, Role
from app.models import (
    AuditLog,
    ComplianceCase,
    Document,
    Entity,
    GSTRegistration,
    ReturnItem,
    StatusTransition,
    TaxPeriod,
    User,
)
from app.schemas.requests import AssignRequest, CaseCreate, TransitionRequest
from app.services import audit, periods, workflow
from app.services.permissions import (
    assert_client_access,
    get_case_or_403,
    get_gstin_or_403,
    get_return_item_or_403,
    require_ca,
    visible_client_ids,
)

router = APIRouter(prefix="/api", tags=["compliance"])


@router.post("/cases", status_code=201)
def open_month(
    payload: CaseCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    """Opens a GSTIN's tax period and creates its three return tracks."""
    require_ca(user)
    reg = get_gstin_or_403(db, user, payload.gst_registration_id)
    case = periods.get_or_create_case(db, reg.id, payload.year, payload.month)
    audit.record(
        db, user, AuditAction.CREATE, "ComplianceCase",
        f"Compliance month opened for {reg.gstin} {payload.year}-{payload.month:02d}",
        target_id=case.id, client_id=case.client_id, case_id=case.id,
    )
    db.commit()
    return case_out(db, case, user)


@router.get("/cases")
def list_cases(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    client_id: Optional[int] = None,
    gst_registration_id: Optional[int] = None,
    entity_id: Optional[int] = None,
    year: Optional[int] = None,
    month: Optional[int] = None,
    case_status: Optional[CaseStatus] = None,
    return_type: Optional[ReturnType] = None,
    return_status: Optional[ReturnStatus] = None,
    employee_id: Optional[int] = None,
    limit: int = Q(200, le=1000),
):
    stmt = select(ComplianceCase).join(TaxPeriod, TaxPeriod.id == ComplianceCase.tax_period_id)
    ids = visible_client_ids(db, user)
    if ids is not None:
        stmt = stmt.where(ComplianceCase.client_id.in_(ids or [-1]))
    if client_id:
        assert_client_access(db, user, client_id)
        stmt = stmt.where(ComplianceCase.client_id == client_id)
    if gst_registration_id:
        stmt = stmt.where(ComplianceCase.gst_registration_id == gst_registration_id)
    if entity_id:
        stmt = stmt.where(ComplianceCase.entity_id == entity_id)
    if year:
        stmt = stmt.where(TaxPeriod.year == year)
    if month:
        stmt = stmt.where(TaxPeriod.month == month)
    if case_status:
        stmt = stmt.where(ComplianceCase.status == case_status)
    if return_type or return_status or employee_id:
        sub = select(ReturnItem.case_id)
        if return_type:
            sub = sub.where(ReturnItem.return_type == return_type)
        if return_status:
            sub = sub.where(ReturnItem.status == return_status)
        if employee_id:
            sub = sub.where(ReturnItem.assigned_employee_id == employee_id)
        stmt = stmt.where(ComplianceCase.id.in_(sub))

    stmt = stmt.order_by(TaxPeriod.year.desc(), TaxPeriod.month.desc()).limit(limit)
    return [case_out(db, c, user) for c in db.execute(stmt).scalars().all()]


@router.get("/cases/{case_id}")
def get_case(case_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    case = get_case_or_403(db, user, case_id)
    out = case_out(db, case, user, detail=True)
    docs = db.execute(select(Document).where(Document.case_id == case.id)).scalars().all()
    out["documents"] = [document_out(d) for d in docs]
    return out


@router.get("/cases/{case_id}/audit")
def case_audit(case_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    get_case_or_403(db, user, case_id)
    logs = db.execute(
        select(AuditLog).where(AuditLog.case_id == case_id).order_by(AuditLog.created_at.desc())
    ).scalars().all()
    return [audit_out(log) for log in logs]


@router.get("/return-items/{item_id}")
def get_return_item(
    item_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    item = get_return_item_or_403(db, user, item_id)
    out = return_item_out(item, user)
    docs = db.execute(
        select(Document).where(Document.return_item_id == item.id)
    ).scalars().all()
    out["documents"] = [document_out(d) for d in docs]
    out["transitions"] = [
        {
            "id": t.id,
            "from_status": t.from_status,
            "to_status": t.to_status,
            "note": t.note,
            "actor_user_id": t.actor_user_id,
            "created_at": t.created_at,
        }
        for t in sorted(item.transitions, key=lambda t: t.created_at)
    ]
    return out


@router.post("/return-items/{item_id}/transition")
def do_transition(
    item_id: int,
    payload: TransitionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    item = get_return_item_or_403(db, user, item_id)
    # These two states are consequences of doing the work, not choices: filing
    # needs an ARN, and AWAITING_PAYMENT means a challan exists. Reaching them
    # by a bare status hop would leave those records missing.
    if payload.to_status == ReturnStatus.FILED:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Record the filing with its ARN instead of setting this status directly",
        )
    if payload.to_status == ReturnStatus.AWAITING_PAYMENT:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Upload the challan instead of setting this status directly",
        )
    if (
        ReturnStatus(item.status) == ReturnStatus.AWAITING_PAYMENT
        and payload.to_status == ReturnStatus.VERIFIED
    ):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Record the payment confirmation instead of setting this status directly",
        )
    workflow.transition(db, user, item, payload.to_status, payload.note, payload.override)
    db.commit()
    db.refresh(item)
    return return_item_out(item, user)


@router.patch("/return-items/{item_id}/assign")
def assign_return_item(
    item_id: int,
    payload: AssignRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_ca(user)
    item = get_return_item_or_403(db, user, item_id)
    if payload.assigned_employee_id is not None:
        item.assigned_employee_id = payload.assigned_employee_id
        item.assignment_is_explicit = True
    if payload.due_date is not None:
        item.due_date = payload.due_date
    if payload.priority is not None:
        item.priority = payload.priority
    audit.record(
        db, user, AuditAction.ASSIGNED, "ReturnItem",
        f"{item.return_type} assignment updated",
        target_id=item.id, client_id=item.case.client_id, case_id=item.case_id,
        meta=payload.model_dump(mode="json"),
    )
    db.commit()
    db.refresh(item)
    return return_item_out(item, user)


@router.get("/periods")
def list_periods(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from app.api.serializers import period_out

    rows = db.execute(
        select(TaxPeriod).order_by(TaxPeriod.year.desc(), TaxPeriod.month.desc())
    ).scalars().all()
    return [period_out(p) for p in rows]
