from __future__ import annotations

import io
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.serializers import document_out, version_out
from app.core.db import get_db
from app.core.enums import (
    CLIENT_SUPPLIED_DOCS,
    DEDICATED_UPLOAD_DOCS,
    AuditAction,
    DocumentType,
    DocumentVersionStatus,
    InvoiceSource,
    ReturnStatus,
    ReturnType,
    Role,
)
from app.models import ComplianceCase, Document, DocumentVersion, InvoiceRecord, ReturnItem, User
from app.services import audit, documents, parser, workflow
from app.services.permissions import (
    assert_client_access,
    get_case_or_403,
    get_document_or_403,
    require_ca,
)
from app.storage import get_storage

router = APIRouter(prefix="/api", tags=["documents"])

# Which document type feeds which workflow track and invoice source.
DOC_RETURN_TYPE = {
    DocumentType.GSTR1_DATA: ReturnType.GSTR1,
    DocumentType.GSTR3B_DATA: ReturnType.GSTR3B,
    DocumentType.PURCHASE_REGISTER: ReturnType.PR_RECON,
    DocumentType.GSTR2B: ReturnType.PR_RECON,
    DocumentType.CHALLAN: ReturnType.GSTR3B,
    DocumentType.PAYMENT_PROOF: ReturnType.GSTR3B,
}
DOC_INVOICE_SOURCE = {
    DocumentType.GSTR1_DATA: InvoiceSource.GSTR1_SALES,
    DocumentType.PURCHASE_REGISTER: InvoiceSource.PURCHASE_REGISTER,
    DocumentType.GSTR2B: InvoiceSource.GSTR2B,
}
EXCEL_SUFFIXES = (".xlsx", ".xlsm")

# Uploading one of these IS the client's data landing for that track, whoever
# physically pressed the button. CA staff doing it for the client is the same
# event -- only the provenance recorded on the version differs.
STAGE_DATA_DOCS = {
    DocumentType.GSTR1_DATA,
    DocumentType.GSTR3B_DATA,
    DocumentType.PURCHASE_REGISTER,
}


def _resolve_return_item(
    db: Session, case: ComplianceCase, doc_type: DocumentType, return_item_id: Optional[int]
) -> Optional[ReturnItem]:
    if return_item_id:
        item = db.get(ReturnItem, return_item_id)
        if not item or item.case_id != case.id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Return item does not belong to case")
        return item
    rt = DOC_RETURN_TYPE.get(doc_type)
    if not rt:
        return None
    return db.execute(
        select(ReturnItem).where(ReturnItem.case_id == case.id, ReturnItem.return_type == rt)
    ).scalars().first()


@router.post("/cases/{case_id}/documents", status_code=201)
async def upload_document(
    case_id: int,
    doc_type: DocumentType = Form(...),
    file: UploadFile = File(...),
    return_item_id: Optional[int] = Form(None),
    remarks: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    case = get_case_or_403(db, user, case_id)
    if doc_type in DEDICATED_UPLOAD_DOCS:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{doc_type.value} is uploaded through its own action, which also "
            "moves the return forward",
        )
    is_client = Role(user.role) == Role.CLIENT
    if is_client and doc_type not in CLIENT_SUPPLIED_DOCS:
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Clients may not upload {doc_type.value}")

    # CA staff uploading a client-supplied document is by definition doing it
    # on the client's behalf -- no checkbox needed to say so.
    on_behalf = not is_client and doc_type in CLIENT_SUPPLIED_DOCS

    data = await file.read()
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Empty file")

    item = _resolve_return_item(db, case, doc_type, return_item_id)
    document = documents.get_or_create_document(db, case, doc_type, user, item)
    version = documents.add_version(
        db, user, document, file.filename, data, file.content_type or "", on_behalf, remarks
    )

    parse_report = None
    source = DOC_INVOICE_SOURCE.get(doc_type)
    if source and file.filename.lower().endswith(EXCEL_SUFFIXES):
        parse_report = _ingest_invoices(db, case, version, source, data)

    if item:
        _advance_workflow(db, user, item, doc_type)

    db.commit()
    db.refresh(version)
    out = version_out(version)
    out["document"] = document_out(document, versions=False)
    out["parse_report"] = parse_report
    return out


def _ingest_invoices(
    db: Session,
    case: ComplianceCase,
    version: DocumentVersion,
    source: InvoiceSource,
    data: bytes,
) -> dict:
    """Parses the workbook into invoice rows. A parse failure never blocks the
    upload -- the file is stored and the report surfaces the problem."""
    try:
        result = parser.parse_invoice_workbook(data, source)
    except Exception as exc:
        return {"records": 0, "errors": [f"Could not parse workbook: {exc}"]}

    for rec in result["records"]:
        db.add(
            InvoiceRecord(
                case_id=case.id,
                source=source,
                document_version_id=version.id,
                **rec,
            )
        )
    db.flush()
    return {
        "records": len(result["records"]),
        "errors": result["errors"],
        "header_row": result["header_row"],
        "mapped_columns": list(result["mapped_columns"].keys()),
        "unmapped_headers": result["unmapped_headers"],
    }


def _advance_workflow(db: Session, user: User, item: ReturnItem, doc_type: DocumentType) -> None:
    """Keyed on what was uploaded, not on who uploaded it. GSTR-2B is CA-supplied
    and never counts as the client's submission, so it is simply not in the set."""
    if doc_type in STAGE_DATA_DOCS:
        workflow.mark_data_submitted(db, user, item, note=f"{doc_type.value} uploaded")


@router.get("/cases/{case_id}/documents")
def list_documents(
    case_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    get_case_or_403(db, user, case_id)
    docs = db.execute(select(Document).where(Document.case_id == case_id)).scalars().all()
    return [document_out(d) for d in docs]


@router.get("/documents/{document_id}")
def get_document(
    document_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    doc = get_document_or_403(db, user, document_id)
    return document_out(doc)


@router.get("/documents/versions/{version_id}/download")
def download_version(
    version_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    version = db.get(DocumentVersion, version_id)
    if not version:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Version not found")
    document = db.get(Document, version.document_id)
    case = db.get(ComplianceCase, document.case_id)
    assert_client_access(db, user, case.client_id)

    data = get_storage().read(version.storage_key)
    audit.record(
        db, user, AuditAction.DOWNLOAD, "DocumentVersion",
        f"{document.title} v{version.version_no} downloaded",
        target_id=version.id, client_id=case.client_id, case_id=case.id,
    )
    db.commit()
    return StreamingResponse(
        io.BytesIO(data),
        media_type=version.content_type or "application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{version.original_filename}"'
        },
    )


@router.post("/documents/versions/{version_id}/review")
def review_version(
    version_id: int,
    verified: bool = Form(...),
    remarks: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Marks a specific uploaded version verified or rejected. Return-item
    status is moved separately via the transition endpoint."""
    require_ca(user)
    version = db.get(DocumentVersion, version_id)
    if not version:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Version not found")
    document = db.get(Document, version.document_id)
    case = db.get(ComplianceCase, document.case_id)
    assert_client_access(db, user, case.client_id)

    version.status = (
        DocumentVersionStatus.VERIFIED if verified else DocumentVersionStatus.REJECTED
    )
    version.remarks = remarks
    audit.record(
        db, user, AuditAction.UPDATE, "DocumentVersion",
        f"{document.title} v{version.version_no} marked {version.status.value}",
        target_id=version.id, client_id=case.client_id, case_id=case.id,
        meta={"remarks": remarks},
    )
    db.commit()
    db.refresh(version)
    return version_out(version)
