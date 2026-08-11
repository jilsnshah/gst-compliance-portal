from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.serializers import return_item_out, version_out
from app.core.db import get_db
from app.core.enums import (
    AuditAction,
    DocumentType,
    NotificationType,
    PaymentStatus,
    ReturnStatus,
    ReturnType,
    Role,
)
from app.models import ComplianceCase, Document, Filing, GSTR3BPayment, ReturnItem, User
from app.schemas.requests import FilingRecord
from app.services import audit, documents, gstr3b as gstr3b_service, notifications, workflow
from app.services.permissions import get_case_or_403, get_return_item_or_403, require_ca

router = APIRouter(prefix="/api", tags=["gstr3b"])


def _latest_version(db: Session, case_id: int, doc_type: DocumentType):
    doc = db.execute(
        select(Document).where(Document.case_id == case_id, Document.doc_type == doc_type)
    ).scalars().first()
    return doc.versions[-1] if doc and doc.versions else None


def _payment_out(db: Session, row: GSTR3BPayment) -> dict:
    """Everything GSTR-3B needs: the challan PDF and whether it has been paid.
    No figures -- the CA reads those on the GST portal."""
    challan = _latest_version(db, row.case_id, DocumentType.CHALLAN)
    proof = _latest_version(db, row.case_id, DocumentType.PAYMENT_PROOF)
    confirmer = db.get(User, row.confirmed_by_user_id) if row.confirmed_by_user_id else None
    return {
        "return_item_id": row.return_item_id,
        "case_id": row.case_id,
        "payment_status": (
            row.payment_status.value
            if hasattr(row.payment_status, "value")
            else row.payment_status
        ),
        "challan": (
            {
                "version_id": challan.id,
                "filename": challan.original_filename,
                "note": challan.remarks,
                "uploaded_at": challan.created_at,
                "download_url": f"/api/documents/versions/{challan.id}/download",
            }
            if challan
            else None
        ),
        "payment": (
            {
                "confirmed_at": row.confirmed_at,
                "confirmed_by": confirmer.full_name if confirmer else None,
                "reference": row.reference,
                "note": row.note,
                "proof": (
                    {
                        "version_id": proof.id,
                        "filename": proof.original_filename,
                        "download_url": f"/api/documents/versions/{proof.id}/download",
                    }
                    if proof
                    else None
                ),
            }
            if row.confirmed_at
            else None
        ),
    }


@router.get("/cases/{case_id}/gstr3b")
def get_gstr3b(
    case_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    case = get_case_or_403(db, user, case_id)
    row = gstr3b_service.get_or_create_payment(db, case, user)
    db.commit()
    return _payment_out(db, row)


@router.post("/return-items/{item_id}/challan", status_code=201)
async def upload_challan(
    item_id: int,
    file: UploadFile = File(...),
    note: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """The CA uploads the challan PDF downloaded from the GST portal. That
    upload is the statement that tax is payable -- it is what puts the return
    into AWAITING_PAYMENT."""
    require_ca(user)
    item = get_return_item_or_403(db, user, item_id)
    if ReturnType(item.return_type) != ReturnType.GSTR3B:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Challans belong to GSTR-3B")
    case = db.get(ComplianceCase, item.case_id)

    data = await file.read()
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Empty file")

    document = documents.get_or_create_document(
        db, case, DocumentType.CHALLAN, user, item, title="GST Challan"
    )
    version = documents.add_version(
        db, user, document, file.filename, data, file.content_type or "application/pdf",
        remarks=note,
    )

    row = gstr3b_service.get_or_create_payment(db, case, user)
    row.payment_status = PaymentStatus.CHALLAN_ISSUED
    workflow.transition(db, user, item, ReturnStatus.AWAITING_PAYMENT, note="Challan uploaded")

    audit.record(
        db, user, AuditAction.CHALLAN_ISSUED, "Document", f"Challan uploaded: {file.filename}",
        target_id=version.id, client_id=case.client_id, case_id=case.id,
    )
    notifications.notify(
        db, NotificationType.CHALLAN_ISSUED, title="GST payment required",
        body="The challan is ready to download in your portal.",
        case=case, return_item=item, to_client=True, exclude_user_id=user.id,
    )
    db.commit()
    return _payment_out(db, row)


@router.post("/return-items/{item_id}/payment-confirmation", status_code=201)
async def confirm_payment(
    item_id: int,
    reference: Optional[str] = Form(None),
    note: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """The client says they have paid on the GST portal. That confirmation is
    what clears the return for filing; CA staff may record it for them."""
    item = get_return_item_or_403(db, user, item_id)
    case = db.get(ComplianceCase, item.case_id)
    row = gstr3b_service.get_or_create_payment(db, case, user)

    if ReturnStatus(item.status) != ReturnStatus.AWAITING_PAYMENT:
        raise HTTPException(status.HTTP_409_CONFLICT, "No challan is awaiting payment")

    if file is not None and file.filename:
        data = await file.read()
        if data:
            proof_doc = documents.get_or_create_document(
                db, case, DocumentType.PAYMENT_PROOF, user, item, title="Payment proof"
            )
            documents.add_version(
                db, user, proof_doc, file.filename, data, file.content_type or "",
                on_behalf_of_client=Role(user.role) != Role.CLIENT,
            )

    row.confirmed_by_user_id = user.id
    row.confirmed_at = datetime.utcnow()
    row.reference = reference
    row.note = note
    row.payment_status = PaymentStatus.PAYMENT_CONFIRMED

    workflow.transition(db, user, item, ReturnStatus.VERIFIED, note="Payment confirmed")

    audit.record(
        db, user, AuditAction.PAYMENT_CONFIRMED, "GSTR3BPayment",
        f"Payment confirmed by {user.full_name}" + (f" (ref {reference})" if reference else ""),
        target_id=row.id, client_id=case.client_id, case_id=case.id,
    )
    notifications.notify(
        db, NotificationType.PAYMENT_CONFIRMED, title="GST payment confirmed",
        body=reference or "", case=case, return_item=item,
        to_ca=True, to_client=Role(user.role) != Role.CLIENT, exclude_user_id=user.id,
    )
    db.commit()
    return _payment_out(db, row)


# ------------------------------------------------------- filing & ack
@router.post("/return-items/{item_id}/file")
def record_filing(
    item_id: int,
    payload: FilingRecord,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Records that the return was filed on the GST portal. The portal remains
    the system of filing; this portal is the system of record."""
    require_ca(user)
    item = get_return_item_or_403(db, user, item_id)
    case = db.get(ComplianceCase, item.case_id)

    if ReturnStatus(item.status) != ReturnStatus.VERIFIED:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Sign the return off before recording the filing"
        )

    filing = db.execute(select(Filing).where(Filing.return_item_id == item.id)).scalars().first()
    if not filing:
        filing = Filing(case_id=case.id, return_item_id=item.id, filed_by_user_id=user.id)
        db.add(filing)
    filing.arn = payload.arn
    filing.filed_on = payload.filed_on or date.today()
    filing.portal_reference = payload.portal_reference
    db.flush()

    workflow.transition(
        db, user, item, ReturnStatus.FILED, note=f"Filed on portal. ARN {payload.arn or '-'}"
    )
    audit.record(
        db, user, AuditAction.FILED, "Filing",
        f"{item.return_type} filed. ARN {payload.arn or '-'}",
        target_id=filing.id, client_id=case.client_id, case_id=case.id,
    )
    db.commit()
    db.refresh(item)
    return return_item_out(item, user)


@router.post("/return-items/{item_id}/acknowledgement")
async def upload_acknowledgement(
    item_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_ca(user)
    item = get_return_item_or_403(db, user, item_id)
    case = db.get(ComplianceCase, item.case_id)

    data = await file.read()
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Empty file")

    document = documents.get_or_create_document(
        db, case, DocumentType.ACKNOWLEDGEMENT, user, item,
        title=f"{item.return_type} Acknowledgement",
    )
    version = documents.add_version(
        db, user, document, file.filename, data, file.content_type or "application/pdf"
    )

    filing = db.execute(select(Filing).where(Filing.return_item_id == item.id)).scalars().first()
    if filing:
        filing.acknowledgement_document_id = document.id

    notifications.notify(
        db, NotificationType.ACKNOWLEDGEMENT_UPLOADED,
        title=f"{item.return_type} acknowledgement available",
        body=file.filename, case=case, return_item=item, to_client=True,
        exclude_user_id=user.id,
    )
    db.commit()
    db.refresh(item)
    out = return_item_out(item, user)
    out["acknowledgement"] = version_out(version)
    return out


@router.get("/return-items/{item_id}/filing")
def get_filing(
    item_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    item = get_return_item_or_403(db, user, item_id)
    filing = db.execute(select(Filing).where(Filing.return_item_id == item.id)).scalars().first()
    if not filing:
        return None
    ack_doc = (
        db.get(Document, filing.acknowledgement_document_id)
        if filing.acknowledgement_document_id
        else None
    )
    return {
        "id": filing.id,
        "arn": filing.arn,
        "filed_on": filing.filed_on,
        "portal_reference": filing.portal_reference,
        "acknowledgement": (
            version_out(ack_doc.versions[-1]) if ack_doc and ack_doc.versions else None
        ),
    }
