from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import (
    AuditAction,
    MismatchResolution,
    NotificationType,
    QueryStatus,
    Role,
)
from app.models import (
    ComplianceCase,
    Conversation,
    InvoiceMatch,
    InvoiceRecord,
    Message,
    MessageAttachment,
    Query,
    ReturnItem,
    TaxPeriod,
    User,
)
from app.services import audit, notifications, workflow


def get_or_create_conversation(
    db: Session,
    user: User,
    subject: str,
    client_id: int,
    case_id: Optional[int] = None,
    return_item_id: Optional[int] = None,
    document_id: Optional[int] = None,
    invoice_match_id: Optional[int] = None,
) -> Conversation:
    """Threads are keyed by their anchor, never chosen by a person: one per
    return item, one per invoice mismatch. Nobody picks or names a thread."""
    existing = db.execute(
        select(Conversation).where(
            Conversation.client_id == client_id,
            Conversation.invoice_match_id == invoice_match_id,
            Conversation.return_item_id == return_item_id,
            Conversation.document_id == document_id,
            Conversation.case_id == case_id,
        )
    ).scalars().first()
    if existing:
        return existing
    conv = Conversation(
        client_id=client_id,
        case_id=case_id,
        return_item_id=return_item_id,
        document_id=document_id,
        invoice_match_id=invoice_match_id,
        subject=subject,
        created_by_user_id=user.id,
    )
    db.add(conv)
    db.flush()
    return conv


def post_message(
    db: Session,
    user: User,
    conv: Conversation,
    body: str,
    is_internal_note: bool = False,
    document_version_ids: Optional[list] = None,
) -> Message:
    msg = Message(
        conversation_id=conv.id,
        author_user_id=user.id,
        body=body,
        is_internal_note=is_internal_note and Role(user.role) != Role.CLIENT,
    )
    db.add(msg)
    db.flush()
    for vid in document_version_ids or []:
        db.add(MessageAttachment(message_id=msg.id, document_version_id=vid))
    conv.last_message_at = datetime.utcnow()

    case = db.get(ComplianceCase, conv.case_id) if conv.case_id else None
    audit.record(
        db, user, AuditAction.MESSAGE_POSTED, "Message", f"Message posted on '{conv.subject}'",
        target_id=msg.id, client_id=conv.client_id, case_id=conv.case_id,
    )
    if not msg.is_internal_note:
        notifications.notify(
            db,
            NotificationType.MESSAGE_POSTED,
            title=conv.subject,
            body=body[:200],
            case=case,
            conversation_id=conv.id,
            client_id=conv.client_id,
            to_client=True,
            to_ca=True,
            exclude_user_id=user.id,
        )
    db.flush()
    return msg


# ------------------------------------------------------------- anchors
def for_return_item(db: Session, user: User, item: ReturnItem) -> Conversation:
    case = db.get(ComplianceCase, item.case_id)
    period = db.get(TaxPeriod, case.tax_period_id)
    label = item.return_type.value if hasattr(item.return_type, "value") else item.return_type
    return get_or_create_conversation(
        db, user, f"{label} — {period.label}", case.client_id,
        case_id=case.id, return_item_id=item.id,
    )


def for_match(db: Session, user: User, match: InvoiceMatch) -> Conversation:
    case = db.get(ComplianceCase, match.case_id)
    record = db.get(InvoiceRecord, match.pr_record_id or match.gstr2b_record_id)
    invoice_no = record.invoice_no if record else match.id
    return get_or_create_conversation(
        db, user, f"Invoice {invoice_no}", case.client_id,
        case_id=case.id, return_item_id=None, invoice_match_id=match.id,
    )


# --------------------------------------------------------------- queries
def raise_query(
    db: Session,
    user: User,
    item: ReturnItem,
    title: str,
    body: Optional[str] = None,
    requires_revision: bool = False,
    invoice_match_id: Optional[int] = None,
    document_version_id: Optional[int] = None,
) -> Query:
    """A query is just a message flagged as blocking: it posts into the stage's
    discussion and moves the return item into a waiting state."""
    case = db.get(ComplianceCase, item.case_id)
    workflow.ensure_review_started(db, user, item)

    if invoice_match_id:
        match = db.get(InvoiceMatch, invoice_match_id)
        conv = for_match(db, user, match)
    else:
        conv = for_return_item(db, user, item)

    q = Query(
        case_id=case.id,
        return_item_id=item.id,
        document_version_id=document_version_id,
        invoice_match_id=invoice_match_id,
        conversation_id=conv.id,
        title=title,
        body=body,
        requires_revision=requires_revision,
        raised_by_user_id=user.id,
    )
    db.add(q)
    db.flush()

    post_message(db, user, conv, body or title)

    if invoice_match_id:
        match = db.get(InvoiceMatch, invoice_match_id)
        if match:
            match.resolution_status = MismatchResolution.IN_PROGRESS
            match.ca_remark = body or title

    audit.record(
        db, user, AuditAction.QUERY_RAISED, "Query", f"Query raised: {title}",
        target_id=q.id, client_id=case.client_id, case_id=case.id,
    )
    notifications.notify(
        db, NotificationType.QUERY_RAISED, title=f"Action needed: {title}", body=body or "",
        case=case, return_item=item, conversation_id=conv.id, to_client=True,
        exclude_user_id=user.id,
    )
    return q


def answer_open_queries(db: Session, user: User, conv: Conversation, body: str) -> list:
    """A client reply is the answer -- no separate 'respond to query' control."""
    queries = db.execute(
        select(Query).where(
            Query.conversation_id == conv.id, Query.status == QueryStatus.OPEN
        )
    ).scalars().all()
    if not queries:
        return []

    case = db.get(ComplianceCase, conv.case_id) if conv.case_id else None
    for q in queries:
        q.status = QueryStatus.ANSWERED
        q.answered_at = datetime.utcnow()
        if q.invoice_match_id:
            match = db.get(InvoiceMatch, q.invoice_match_id)
            if match:
                match.client_response = body
                match.resolution_status = MismatchResolution.CLIENT_RESPONDED
        audit.record(
            db, user, AuditAction.QUERY_ANSWERED, "Query", f"Query answered: {q.title}",
            target_id=q.id, client_id=conv.client_id, case_id=conv.case_id,
        )
    notifications.notify(
        db, NotificationType.QUERY_ANSWERED,
        title=f"Client responded: {queries[0].title}", body=body[:200],
        case=case, conversation_id=conv.id, to_ca=True, exclude_user_id=user.id,
    )
    return queries
