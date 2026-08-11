from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import (
    CLIENT_STATUS_LABELS,
    RETURN_LABELS,
    QueryStatus,
    ReturnStatus,
    ReturnType,
    Role,
    is_terminal,
    track_key,
)
from app.models import (
    Client,
    ComplianceCase,
    Conversation,
    Document,
    DocumentVersion,
    Employee,
    Entity,
    InvoiceMatch,
    Message,
    Notification,
    Query,
    ReturnItem,
    TaxPeriod,
    User,
)
from app.services.workflow import (
    allowed_next,
    client_visible_status,
    pending_prerequisites,
    progress_for,
)


def _val(enum_or_str):
    return enum_or_str.value if hasattr(enum_or_str, "value") else enum_or_str


def user_out(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "phone": user.phone,
        "role": _val(user.role),
        "is_active": user.is_active,
        "employee_id": user.employee.id if user.employee else None,
        "client_ids": [link.client_id for link in user.client_links],
    }


def client_out(client: Client) -> dict:
    """The login email comes from the linked user, which is the only place it
    is stored."""
    login = client.user_links[0].user if client.user_links else None
    return {
        "id": client.id,
        "name": client.name,
        "phone": client.phone,
        "email": login.email if login else None,
        "login_user_id": login.id if login else None,
        "is_active": client.is_active,
        "entity_count": len(client.entities),
    }


def entity_out(entity: Entity) -> dict:
    return {
        "id": entity.id,
        "client_id": entity.client_id,
        "file_number": entity.file_number,
        "legal_name": entity.legal_name,
        "trade_name": entity.trade_name,
        "pan": entity.pan,
        "constitution": _val(entity.constitution),
        "address": {
            "line1": entity.address_line1,
            "line2": entity.address_line2,
            "city": entity.city,
            "state": entity.state,
            "pincode": entity.pincode,
        },
        "contact_person": entity.contact_person,
        "contact_phone": entity.contact_phone,
        "contact_email": entity.contact_email,
        "applicable_services": entity.applicable_services or [],
        "is_active": entity.is_active,
        "gstin": entity.gstin,
        "state_code": entity.state_code,
        "state_name": entity.state_name,
        "registration_date": entity.registration_date,
        "filing_frequency": _val(entity.filing_frequency),
        "assigned_employee_id": entity.assigned_employee_id,
    }


def employee_out(emp: Employee) -> dict:
    return {
        "id": emp.id,
        "user_id": emp.user_id,
        "employee_code": emp.employee_code,
        "designation": emp.designation,
        "is_active": emp.is_active,
        "full_name": emp.user.full_name if emp.user else None,
        "email": emp.user.email if emp.user else None,
    }


def period_out(period: TaxPeriod) -> dict:
    return {
        "id": period.id,
        "code": period.code,
        "label": period.label,
        "year": period.year,
        "month": period.month,
        "gstr1_due_date": period.gstr1_due_date,
        "gstr3b_due_date": period.gstr3b_due_date,
    }


def waiting_on_client_ids(db: Session, case_id: int) -> set:
    """Return items with an unanswered query. This is what replaced the old
    QUERY_RAISED / REVISION_REQUIRED states -- derived, never stored."""
    rows = db.execute(
        select(Query.return_item_id).where(
            Query.case_id == case_id, Query.status == QueryStatus.OPEN
        )
    ).scalars()
    return set(rows)


def return_item_out(
    item: ReturnItem,
    viewer: User,
    waiting_on_client: bool = False,
    blocked_reason: Optional[str] = None,
) -> dict:
    internal = ReturnStatus(item.status)
    visible = client_visible_status(item.return_type, internal, waiting_on_client)
    is_client = Role(viewer.role) == Role.CLIENT
    terminal = is_terminal(item.return_type, internal)
    out = {
        "id": item.id,
        "case_id": item.case_id,
        "return_type": _val(item.return_type),
        "return_label": RETURN_LABELS[ReturnType(item.return_type)],
        "status": visible.value if is_client else internal.value,
        "status_label": CLIENT_STATUS_LABELS[visible] if is_client else internal.value.replace("_", " ").title(),
        "client_status": visible.value,
        "client_status_label": CLIENT_STATUS_LABELS[visible],
        "progress": progress_for(item.return_type, internal),
        "is_terminal": terminal,
        "waiting_on": "CLIENT" if visible.value == "ACTION_NEEDED" else ("NOBODY" if terminal else "CA"),
        "has_open_query": waiting_on_client,
        "due_date": item.due_date,
        "priority": item.priority,
        "assigned_employee_id": item.assigned_employee_id,
        "assignment_is_explicit": item.assignment_is_explicit,
        "review_started_at": item.review_started_at,
        "review_started_by": item.reviewer.full_name if item.reviewer else None,
        "updated_at": item.updated_at,
        # A gated stage advertises no forward actions -- only the reason.
        "allowed_next": (
            [] if blocked_reason else allowed_next(item.return_type, internal, Role(viewer.role))
        ),
        "blocked_reason": blocked_reason,
    }
    if not is_client:
        out["internal_status"] = internal.value
        out["internal_remarks"] = item.internal_remarks
    return out


def _gstr3b_blocked_reason(case: ComplianceCase) -> Optional[str]:
    """Same wording the engine would reject with, so the screen and the API
    error can never say different things."""
    pending = pending_prerequisites(case.return_items)
    if not pending:
        return None
    return "Waiting because " + ", and ".join(pending)


def case_out(db: Session, case: ComplianceCase, viewer: User, detail: bool = False) -> dict:
    period = db.get(TaxPeriod, case.tax_period_id)
    entity = db.get(Entity, case.entity_id)
    client = db.get(Client, case.client_id)
    waiting = waiting_on_client_ids(db, case.id)
    blocked = _gstr3b_blocked_reason(case)
    out = {
        "id": case.id,
        "status": _val(case.status),
        "client": {"id": client.id, "name": client.name},
        "entity": {
            "id": entity.id,
            "legal_name": entity.legal_name,
            "trade_name": entity.trade_name,
            "file_number": entity.file_number,
        },
        "gstin": entity.gstin,
        "period": period_out(period),
        "created_at": case.created_at,
        "completed_at": case.completed_at,
        "returns": [
            return_item_out(
                i,
                viewer,
                i.id in waiting,
                blocked if ReturnType(i.return_type) == ReturnType.GSTR3B else None,
            )
            for i in case.return_items
        ],
    }
    return out


def document_out(doc: Document, versions: bool = True) -> dict:
    out = {
        "id": doc.id,
        "case_id": doc.case_id,
        "return_item_id": doc.return_item_id,
        "doc_type": _val(doc.doc_type),
        "title": doc.title,
        "current_version_no": doc.current_version_no,
        "created_at": doc.created_at,
    }
    if versions:
        out["versions"] = [version_out(v) for v in doc.versions]
    return out


def version_out(version: DocumentVersion) -> dict:
    return {
        "id": version.id,
        "document_id": version.document_id,
        "version_no": version.version_no,
        "original_filename": version.original_filename,
        "content_type": version.content_type,
        "size_bytes": version.size_bytes,
        "status": _val(version.status),
        "remarks": version.remarks,
        "uploaded_by_user_id": version.uploaded_by_user_id,
        "uploaded_by_name": version.uploader.full_name if version.uploader else None,
        "uploaded_by_role": _val(version.uploader.role) if version.uploader else None,
        "uploaded_on_behalf_of_client": version.uploaded_on_behalf_of_client,
        "created_at": version.created_at,
        "download_url": f"/api/documents/versions/{version.id}/download",
    }


def query_out(q: Query) -> dict:
    return {
        "id": q.id,
        "case_id": q.case_id,
        "return_item_id": q.return_item_id,
        "document_version_id": q.document_version_id,
        "invoice_match_id": q.invoice_match_id,
        "conversation_id": q.conversation_id,
        "title": q.title,
        "body": q.body,
        "status": _val(q.status),
        "requires_revision": q.requires_revision,
        "raised_by_user_id": q.raised_by_user_id,
        "created_at": q.created_at,
        "answered_at": q.answered_at,
        "resolved_at": q.resolved_at,
    }


def message_out(msg: Message, author: Optional[User] = None) -> dict:
    return {
        "id": msg.id,
        "conversation_id": msg.conversation_id,
        "author_user_id": msg.author_user_id,
        "author_name": author.full_name if author else None,
        "author_role": _val(author.role) if author else None,
        "body": msg.body,
        "is_internal_note": msg.is_internal_note,
        "created_at": msg.created_at,
        "attachments": [
            {
                "id": a.id,
                "document_version_id": a.document_version_id,
                "download_url": f"/api/documents/versions/{a.document_version_id}/download",
            }
            for a in msg.attachments
        ],
    }


def conversation_out(conv: Conversation, message_count: int = 0) -> dict:
    return {
        "id": conv.id,
        "client_id": conv.client_id,
        "case_id": conv.case_id,
        "return_item_id": conv.return_item_id,
        "document_id": conv.document_id,
        "invoice_match_id": conv.invoice_match_id,
        "subject": conv.subject,
        "is_closed": conv.is_closed,
        "created_at": conv.created_at,
        "last_message_at": conv.last_message_at,
        "message_count": message_count,
    }


def notification_out(note: Notification) -> dict:
    return {
        "id": note.id,
        "type": _val(note.notification_type),
        "title": note.title,
        "body": note.body,
        "case_id": note.case_id,
        "return_item_id": note.return_item_id,
        "conversation_id": note.conversation_id,
        "is_read": note.is_read,
        "created_at": note.created_at,
    }


def invoice_record_out(rec) -> Optional[dict]:
    if rec is None:
        return None
    return {
        "id": rec.id,
        "source": _val(rec.source),
        "supplier_gstin": rec.supplier_gstin,
        "supplier_name": rec.supplier_name,
        "invoice_no": rec.invoice_no,
        "invoice_date": rec.invoice_date,
        "taxable_value": rec.taxable_value,
        "igst": rec.igst,
        "cgst": rec.cgst,
        "sgst": rec.sgst,
        "cess": rec.cess,
        "total_value": rec.total_value,
        "itc_available": rec.itc_available,
        "source_row_no": rec.source_row_no,
    }


def match_out(match: InvoiceMatch) -> dict:
    return {
        "id": match.id,
        "case_id": match.case_id,
        "run_id": match.run_id,
        "match_status": _val(match.match_status),
        "diff_flags": match.diff_flags or [],
        "taxable_value_diff": match.taxable_value_diff,
        "tax_diff": match.tax_diff,
        "match_score": match.match_score,
        "resolution_status": _val(match.resolution_status),
        "assigned_employee_id": match.assigned_employee_id,
        "ca_remark": match.ca_remark,
        "client_response": match.client_response,
        "resolution_note": match.resolution_note,
        "resolved_at": match.resolved_at,
        "purchase_register": invoice_record_out(match.pr_record),
        "gstr2b": invoice_record_out(match.gstr2b_record),
    }


def audit_out(log) -> dict:
    return {
        "id": log.id,
        "actor_name": log.actor_name,
        "actor_role": log.actor_role,
        "action": _val(log.action),
        "target_type": log.target_type,
        "target_id": log.target_id,
        "description": log.description,
        "meta": log.meta,
        "case_id": log.case_id,
        "created_at": log.created_at,
    }
