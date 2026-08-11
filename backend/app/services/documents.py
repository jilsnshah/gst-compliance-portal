from __future__ import annotations

import hashlib
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import (
    REVIEWABLE_DOCS,
    AuditAction,
    DocumentType,
    DocumentVersionStatus,
    NotificationType,
    Role,
)
from app.models import (
    ComplianceCase,
    Document,
    DocumentVersion,
    Entity,
    ReturnItem,
    TaxPeriod,
    User,
)
from app.services import audit, notifications
from app.storage import build_key, get_storage


def get_or_create_document(
    db: Session,
    case: ComplianceCase,
    doc_type: DocumentType,
    user: User,
    return_item: Optional[ReturnItem] = None,
    title: Optional[str] = None,
) -> Document:
    """One document slot per (case, return item, type) so revisions stack as
    versions instead of piling up as unrelated files."""
    stmt = select(Document).where(
        Document.case_id == case.id, Document.doc_type == doc_type
    )
    stmt = stmt.where(
        Document.return_item_id == (return_item.id if return_item else None)
    )
    doc = db.execute(stmt).scalars().first()
    if doc:
        return doc

    doc = Document(
        case_id=case.id,
        return_item_id=return_item.id if return_item else None,
        doc_type=doc_type,
        title=title or doc_type.value.replace("_", " ").title(),
        created_by_user_id=user.id,
    )
    db.add(doc)
    db.flush()
    return doc


def add_version(
    db: Session,
    user: User,
    document: Document,
    filename: str,
    data: bytes,
    content_type: str = "",
    on_behalf_of_client: bool = False,
    remarks: Optional[str] = None,
) -> DocumentVersion:
    """Never overwrites. Previous versions are marked superseded but stay
    downloadable forever."""
    case = db.get(ComplianceCase, document.case_id)
    entity = db.get(Entity, case.entity_id)
    period = db.get(TaxPeriod, case.tax_period_id)

    reviewable = DocumentType(document.doc_type) in REVIEWABLE_DOCS
    for old in document.versions:
        if reviewable and old.status not in (
            DocumentVersionStatus.VERIFIED,
            DocumentVersionStatus.REJECTED,
        ):
            old.status = DocumentVersionStatus.SUPERSEDED

    version_no = document.current_version_no + 1
    doc_type_value = (
        document.doc_type.value if hasattr(document.doc_type, "value") else str(document.doc_type)
    )
    key = build_key(case.client_id, entity.gstin, period.code, doc_type_value, version_no, filename)
    get_storage().put(key, data, content_type)

    version = DocumentVersion(
        document_id=document.id,
        version_no=version_no,
        original_filename=filename,
        storage_key=key,
        content_type=content_type,
        size_bytes=len(data),
        checksum=hashlib.sha256(data).hexdigest(),
        uploaded_by_user_id=user.id,
        uploaded_on_behalf_of_client=on_behalf_of_client,
        status=(
            DocumentVersionStatus.PENDING_REVIEW
            if reviewable
            else DocumentVersionStatus.NOT_APPLICABLE
        ),
        remarks=remarks,
    )
    db.add(version)
    document.current_version_no = version_no
    db.flush()

    by = "CA (on behalf of client)" if on_behalf_of_client else user.role
    audit.record(
        db,
        user,
        AuditAction.UPLOAD,
        "DocumentVersion",
        f"{document.title} v{version_no} uploaded by {by}: {filename}",
        target_id=version.id,
        client_id=case.client_id,
        case_id=case.id,
        meta={"document_id": document.id, "version": version_no, "size": len(data)},
    )
    return_item = db.get(ReturnItem, document.return_item_id) if document.return_item_id else None
    notifications.notify(
        db,
        NotificationType.DOCUMENT_UPLOADED,
        title=f"{document.title} v{version_no} uploaded",
        body=filename,
        case=case,
        return_item=return_item,
        to_ca=True,
        to_client=Role(user.role) != Role.CLIENT,
        exclude_user_id=user.id,
    )
    return version


def latest_version(document: Document) -> Optional[DocumentVersion]:
    return document.versions[-1] if document.versions else None
