from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.serializers import query_out
from app.core.db import get_db
from app.core.enums import AuditAction, MismatchResolution, QueryStatus
from app.models import ComplianceCase, Conversation, InvoiceMatch, Query, User
from app.schemas.requests import QueryAnswer, QueryCreate
from app.services import audit, discussion
from app.services.permissions import (
    get_return_item_or_403,
    require_ca,
    visible_client_ids,
)

router = APIRouter(prefix="/api", tags=["queries"])


@router.post("/queries", status_code=201)
def raise_query(
    payload: QueryCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    require_ca(user)
    item = get_return_item_or_403(db, user, payload.return_item_id)
    q = discussion.raise_query(
        db,
        user,
        item,
        title=payload.title,
        body=payload.body,
        requires_revision=payload.requires_revision,
        invoice_match_id=payload.invoice_match_id,
        document_version_id=payload.document_version_id,
    )
    db.commit()
    db.refresh(q)
    return query_out(q)


@router.get("/queries")
def list_queries(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    case_id: Optional[int] = None,
    return_item_id: Optional[int] = None,
    query_status: Optional[QueryStatus] = None,
    open_only: bool = False,
):
    stmt = select(Query).join(ComplianceCase, ComplianceCase.id == Query.case_id)
    ids = visible_client_ids(db, user)
    if ids is not None:
        stmt = stmt.where(ComplianceCase.client_id.in_(ids or [-1]))
    if case_id:
        stmt = stmt.where(Query.case_id == case_id)
    if return_item_id:
        stmt = stmt.where(Query.return_item_id == return_item_id)
    if query_status:
        stmt = stmt.where(Query.status == query_status)
    if open_only:
        stmt = stmt.where(Query.status != QueryStatus.RESOLVED)
    stmt = stmt.order_by(Query.created_at.desc())
    return [query_out(q) for q in db.execute(stmt).scalars().all()]


@router.post("/queries/{query_id}/answer")
def answer_query(
    query_id: int,
    payload: QueryAnswer,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = _get_query_or_403(db, user, query_id)
    conv = db.get(Conversation, q.conversation_id) if q.conversation_id else None
    if conv:
        discussion.post_message(db, user, conv, payload.body)
        discussion.answer_open_queries(db, user, conv, payload.body)
    else:
        q.status = QueryStatus.ANSWERED
        q.answered_at = datetime.utcnow()
    db.commit()
    db.refresh(q)
    return query_out(q)


@router.post("/queries/{query_id}/resolve")
def resolve_query(
    query_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    note: Optional[str] = None,
):
    require_ca(user)
    q = _get_query_or_403(db, user, query_id)
    case = db.get(ComplianceCase, q.case_id)
    q.status = QueryStatus.RESOLVED
    q.resolved_at = datetime.utcnow()
    q.resolved_by_user_id = user.id

    if q.invoice_match_id:
        match = db.get(InvoiceMatch, q.invoice_match_id)
        if match:
            match.resolution_status = MismatchResolution.RESOLVED
            match.resolution_note = note
            match.resolved_at = datetime.utcnow()
            match.resolved_by_user_id = user.id

    audit.record(
        db, user, AuditAction.QUERY_RESOLVED, "Query", f"Query resolved: {q.title}",
        target_id=q.id, client_id=case.client_id, case_id=case.id, meta={"note": note},
    )
    db.commit()
    db.refresh(q)
    return query_out(q)


def _get_query_or_403(db: Session, user: User, query_id: int) -> Query:
    q = db.get(Query, query_id)
    if not q:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Query not found")
    case = db.get(ComplianceCase, q.case_id)
    ids = visible_client_ids(db, user)
    if ids is not None and case.client_id not in ids:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No access to this query")
    return q
