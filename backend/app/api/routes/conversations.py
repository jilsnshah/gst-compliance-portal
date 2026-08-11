from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.serializers import conversation_out, message_out, notification_out
from app.core.db import get_db
from app.core.enums import Role
from app.models import (
    ComplianceCase,
    Conversation,
    InvoiceMatch,
    Message,
    Notification,
    ReturnItem,
    User,
)
from app.schemas.requests import ConversationCreate, MessageCreate
from app.services.discussion import get_or_create_conversation, post_message
from app.services.permissions import assert_client_access, visible_client_ids

router = APIRouter(prefix="/api", tags=["communication"])


def _resolve_client_id(db: Session, payload: ConversationCreate) -> Optional[int]:
    if payload.case_id:
        case = db.get(ComplianceCase, payload.case_id)
        return case.client_id if case else None
    if payload.return_item_id:
        item = db.get(ReturnItem, payload.return_item_id)
        return item.case.client_id if item else None
    if payload.invoice_match_id:
        match = db.get(InvoiceMatch, payload.invoice_match_id)
        if match:
            case = db.get(ComplianceCase, match.case_id)
            return case.client_id
    return payload.client_id


@router.get("/conversations")
def list_conversations(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    case_id: Optional[int] = None,
    return_item_id: Optional[int] = None,
    invoice_match_id: Optional[int] = None,
    client_id: Optional[int] = None,
):
    stmt = select(Conversation).order_by(Conversation.last_message_at.desc())
    ids = visible_client_ids(db, user)
    if ids is not None:
        stmt = stmt.where(Conversation.client_id.in_(ids or [-1]))
    if case_id:
        stmt = stmt.where(Conversation.case_id == case_id)
    if return_item_id:
        stmt = stmt.where(Conversation.return_item_id == return_item_id)
    if invoice_match_id:
        stmt = stmt.where(Conversation.invoice_match_id == invoice_match_id)
    if client_id:
        assert_client_access(db, user, client_id)
        stmt = stmt.where(Conversation.client_id == client_id)

    convs = db.execute(stmt).scalars().all()
    counts = dict(
        db.execute(
            select(Message.conversation_id, func.count(Message.id)).group_by(Message.conversation_id)
        ).all()
    )
    return [conversation_out(c, counts.get(c.id, 0)) for c in convs]


@router.post("/conversations", status_code=201)
def create_conversation(
    payload: ConversationCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    client_id = _resolve_client_id(db, payload)
    if not client_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Could not resolve client for thread")
    assert_client_access(db, user, client_id)
    conv = get_or_create_conversation(
        db, user, payload.subject, client_id, payload.case_id,
        payload.return_item_id, payload.document_id, payload.invoice_match_id,
    )
    db.commit()
    return conversation_out(conv)


@router.get("/conversations/{conversation_id}/messages")
def list_messages(
    conversation_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    conv = db.get(Conversation, conversation_id)
    if not conv:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    assert_client_access(db, user, conv.client_id)

    messages = conv.messages
    if Role(user.role) == Role.CLIENT:
        messages = [m for m in messages if not m.is_internal_note]
    authors = {
        u.id: u
        for u in db.execute(
            select(User).where(User.id.in_([m.author_user_id for m in messages] or [-1]))
        ).scalars()
    }
    return {
        "conversation": conversation_out(conv, len(messages)),
        "messages": [message_out(m, authors.get(m.author_user_id)) for m in messages],
    }


@router.post("/conversations/{conversation_id}/messages", status_code=201)
def create_message(
    conversation_id: int,
    payload: MessageCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conv = db.get(Conversation, conversation_id)
    if not conv:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    assert_client_access(db, user, conv.client_id)
    msg = post_message(
        db, user, conv, payload.body, payload.is_internal_note, payload.document_version_ids
    )
    db.commit()
    db.refresh(msg)
    return message_out(msg, user)


# ---------------------------------------------------------- notifications
@router.get("/notifications")
def list_notifications(
    unread_only: bool = False,
    limit: int = 50,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        stmt = stmt.where(Notification.is_read.is_(False))
    stmt = stmt.order_by(Notification.created_at.desc()).limit(limit)
    rows = db.execute(stmt).scalars().all()
    unread = db.execute(
        select(func.count(Notification.id)).where(
            Notification.user_id == user.id, Notification.is_read.is_(False)
        )
    ).scalar_one()
    return {"unread_count": unread, "items": [notification_out(n) for n in rows]}


@router.post("/notifications/{notification_id}/read")
def mark_read(
    notification_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    note = db.get(Notification, notification_id)
    if not note or note.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notification not found")
    note.is_read = True
    db.commit()
    return {"status": "ok"}


@router.post("/notifications/read-all")
def mark_all_read(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.execute(
        select(Notification).where(
            Notification.user_id == user.id, Notification.is_read.is_(False)
        )
    ).scalars().all()
    for note in rows:
        note.is_read = True
    db.commit()
    return {"status": "ok", "marked": len(rows)}
