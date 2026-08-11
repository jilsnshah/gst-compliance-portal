from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.serializers import message_out, query_out
from app.core.db import get_db
from app.core.enums import (
    RETURN_LABELS,
    AuditAction,
    MismatchResolution,
    QueryStatus,
    ReturnType,
    Role,
)
from app.models import Conversation, InvoiceMatch, Query, ReturnItem, User
from app.services import audit, discussion
from app.services.permissions import get_case_or_403, get_return_item_or_403, require_ca

router = APIRouter(prefix="/api", tags=["discussion"])


class DiscussionPost(BaseModel):
    body: str
    is_internal_note: bool = False
    # Files already uploaded through /cases/{id}/attachments.
    document_version_ids: list = []
    # CA only: flag this message as blocking. The client must respond, and
    # optionally re-upload, before the stage can move on.
    as_query: bool = False
    requires_revision: bool = False


def _payload(db: Session, viewer: User, conv: Conversation) -> dict:
    messages = conv.messages
    if Role(viewer.role) == Role.CLIENT:
        messages = [m for m in messages if not m.is_internal_note]
    authors = {
        u.id: u
        for u in db.execute(
            select(User).where(User.id.in_([m.author_user_id for m in messages] or [-1]))
        ).scalars()
    }
    queries = db.execute(
        select(Query).where(Query.conversation_id == conv.id).order_by(Query.created_at)
    ).scalars().all()
    open_query = next(
        (q for q in reversed(queries) if QueryStatus(q.status) != QueryStatus.RESOLVED), None
    )
    return {
        "conversation_id": conv.id,
        "subject": conv.subject,
        "messages": [message_out(m, authors.get(m.author_user_id)) for m in messages],
        "queries": [query_out(q) for q in queries],
        "open_query": query_out(open_query) if open_query else None,
    }


# ------------------------------------------------- stage-level discussion
@router.get("/return-items/{item_id}/discussion")
def get_stage_discussion(
    item_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    item = get_return_item_or_403(db, user, item_id)
    conv = discussion.for_return_item(db, user, item)
    db.commit()
    return _payload(db, user, conv)


@router.post("/return-items/{item_id}/discussion", status_code=201)
def post_stage_discussion(
    item_id: int,
    payload: DiscussionPost,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """One composer for the whole stage. A CA message can be flagged as a query;
    a client message automatically answers whatever query is open."""
    item = get_return_item_or_403(db, user, item_id)
    is_client = Role(user.role) == Role.CLIENT

    if payload.as_query:
        require_ca(user)
        title = payload.body.strip().split("\n")[0][:120]
        discussion.raise_query(
            db, user, item, title, payload.body, requires_revision=payload.requires_revision
        )
        conv = discussion.for_return_item(db, user, item)
    else:
        conv = discussion.for_return_item(db, user, item)
        discussion.post_message(
            db, user, conv, payload.body, payload.is_internal_note,
            payload.document_version_ids,
        )
        if is_client and not payload.is_internal_note:
            discussion.answer_open_queries(db, user, conv, payload.body)

    db.commit()
    return _payload(db, user, conv)


# ------------------------------------------------ invoice-level discussion
@router.get("/recon/matches/{match_id}/discussion")
def get_match_discussion(
    match_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    match = db.get(InvoiceMatch, match_id)
    if not match:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Match not found")
    get_case_or_403(db, user, match.case_id)
    conv = discussion.for_match(db, user, match)
    db.commit()
    return _payload(db, user, conv)


@router.post("/recon/matches/{match_id}/discussion", status_code=201)
def post_match_discussion(
    match_id: int,
    payload: DiscussionPost,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    match = db.get(InvoiceMatch, match_id)
    if not match:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Match not found")
    get_case_or_403(db, user, match.case_id)
    is_client = Role(user.role) == Role.CLIENT

    if payload.as_query:
        require_ca(user)
        item = db.get(ReturnItem, _recon_item_id(db, match))
        title = payload.body.strip().split("\n")[0][:120]
        discussion.raise_query(
            db, user, item, title, payload.body, invoice_match_id=match.id
        )
        conv = discussion.for_match(db, user, match)
    else:
        conv = discussion.for_match(db, user, match)
        discussion.post_message(
            db, user, conv, payload.body, payload.is_internal_note,
            payload.document_version_ids,
        )
        if is_client and not payload.is_internal_note:
            match.client_response = payload.body
            match.resolution_status = MismatchResolution.CLIENT_RESPONDED
            discussion.answer_open_queries(db, user, conv, payload.body)
        elif not payload.is_internal_note:
            match.ca_remark = payload.body

    db.commit()
    return _payload(db, user, conv)


def _recon_item_id(db: Session, match: InvoiceMatch) -> int:
    from app.core.enums import ReturnType

    item = db.execute(
        select(ReturnItem).where(
            ReturnItem.case_id == match.case_id, ReturnItem.return_type == ReturnType.PR_RECON
        )
    ).scalars().first()
    return item.id


# -------------------------------------------------------------- resolve
@router.post("/queries/{query_id}/close")
def close_query(
    query_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    note: Optional[str] = None,
):
    """CA marks the blocking item cleared. Deliberately the only query control
    left in the UI."""
    require_ca(user)
    q = db.get(Query, query_id)
    if not q:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Query not found")
    case = get_case_or_403(db, user, q.case_id)

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
        target_id=q.id, client_id=case.client_id, case_id=case.id,
    )
    db.commit()
    conv = db.get(Conversation, q.conversation_id)
    return _payload(db, user, conv) if conv else query_out(q)


# ---------------------------------------------------------- attachments
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024


@router.post("/cases/{case_id}/attachments", status_code=201)
async def upload_attachment(
    case_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """A file to hang off a message -- a screenshot of a supplier's invoice, a
    bank advice, whatever makes the point. Stored and versioned like any other
    document so it is downloadable, audited and never overwritten. Both sides
    may attach; the message carries who sent it."""
    from app.core.enums import DocumentType
    from app.services import documents as docs_service
    from app.services.permissions import get_case_or_403

    case = get_case_or_403(db, user, case_id)
    data = await file.read()
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Empty file")
    if len(data) > MAX_ATTACHMENT_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"Attachments are limited to {MAX_ATTACHMENT_BYTES // (1024 * 1024)} MB",
        )

    document = docs_service.get_or_create_document(
        db, case, DocumentType.MESSAGE_ATTACHMENT, user, title="Chat attachments"
    )
    version = docs_service.add_version(
        db, user, document, file.filename, data, file.content_type or ""
    )
    db.commit()
    return {
        "document_version_id": version.id,
        "filename": version.original_filename,
        "size_bytes": version.size_bytes,
        "content_type": version.content_type,
        "download_url": f"/api/documents/versions/{version.id}/download",
    }


# --------------------------------------------------------------- inbox
@router.get("/inbox")
def inbox(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Flat 'what needs me' list. Replaces the thread picker entirely."""
    from app.models import ComplianceCase, TaxPeriod
    from app.services.permissions import visible_client_ids

    stmt = (
        select(Query, ComplianceCase, TaxPeriod, ReturnItem)
        .join(ComplianceCase, ComplianceCase.id == Query.case_id)
        .join(TaxPeriod, TaxPeriod.id == ComplianceCase.tax_period_id)
        .join(ReturnItem, ReturnItem.id == Query.return_item_id)
        .where(Query.status != QueryStatus.RESOLVED)
        .order_by(Query.created_at.desc())
    )
    ids = visible_client_ids(db, user)
    if ids is not None:
        stmt = stmt.where(ComplianceCase.client_id.in_(ids or [-1]))

    is_client = Role(user.role) == Role.CLIENT
    items = []
    for q, case, period, item in db.execute(stmt).all():
        waiting_on = "CLIENT" if QueryStatus(q.status) == QueryStatus.OPEN else "CA"
        items.append({
            "query_id": q.id,
            "title": q.title,
            "body": q.body,
            "status": q.status if isinstance(q.status, str) else q.status.value,
            "waiting_on": waiting_on,
            "mine": (waiting_on == "CLIENT") == is_client,
            "requires_revision": q.requires_revision,
            "created_at": q.created_at,
            "case_id": case.id,
            "period_label": period.label,
            "return_item_id": item.id,
            "return_type": item.return_type if isinstance(item.return_type, str) else item.return_type.value,
            "return_label": RETURN_LABELS[ReturnType(item.return_type)],
            "invoice_match_id": q.invoice_match_id,
        })
    return {"items": items, "waiting_on_me": sum(1 for i in items if i["mine"])}
