from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.db import get_db
from app.core.enums import AuditAction, DocumentType, InvoiceSource
from app.models import ColumnMapping, ComplianceCase, Document, DocumentVersion, InvoiceRecord, User
from app.services import audit, parser
from app.services.permissions import assert_client_access, require_ca
from app.storage import get_storage

router = APIRouter(prefix="/api", tags=["column mappings"])

DOC_SOURCE = {
    DocumentType.PURCHASE_REGISTER: InvoiceSource.PURCHASE_REGISTER,
    DocumentType.GSTR2B: InvoiceSource.GSTR2B,
}


class MappingSpec(BaseModel):
    sheet_name: Optional[str] = None
    header_row: Optional[int] = None
    first_data_row: int = 2
    # field name -> 0-based column index
    columns: dict = {}


class ApplyMapping(BaseModel):
    mapping: Optional[MappingSpec] = None
    mapping_id: Optional[int] = None
    # Remember this layout for the client so next month needs no mapping at all.
    save_as: Optional[str] = None


def _version_or_403(db: Session, user: User, version_id: int):
    version = db.get(DocumentVersion, version_id)
    if not version:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Version not found")
    document = db.get(Document, version.document_id)
    case = db.get(ComplianceCase, document.case_id)
    assert_client_access(db, user, case.client_id)
    return version, document, case


def mapping_out(m: ColumnMapping) -> dict:
    return {
        "id": m.id,
        "client_id": m.client_id,
        "doc_type": m.doc_type if isinstance(m.doc_type, str) else m.doc_type.value,
        "label": m.label,
        "sheet_name": m.sheet_name,
        "header_row": m.header_row,
        "first_data_row": m.first_data_row,
        "columns": m.columns,
        "fingerprint": m.fingerprint,
        "is_default": m.is_default,
        "updated_at": m.updated_at,
    }


@router.get("/documents/versions/{version_id}/preview")
def preview_version(
    version_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    """The raw grid, so the CA can see exactly which column holds what.

    No field detection happens here on purpose: client workbooks have arbitrary
    or missing headers, so the CA states the mapping rather than the software
    guessing it."""
    require_ca(user)
    version, document, case = _version_or_403(db, user, version_id)
    data = get_storage().read(version.storage_key)
    try:
        out = parser.preview_workbook(data)
    except parser.UnreadableFile as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    except Exception:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "This file could not be read as a spreadsheet. Upload .xlsx or CSV.",
        )

    saved = db.execute(
        select(ColumnMapping).where(
            ColumnMapping.client_id == case.client_id,
            ColumnMapping.doc_type == document.doc_type,
        ).order_by(ColumnMapping.is_default.desc(), ColumnMapping.updated_at.desc())
    ).scalars().all()
    out["filename"] = version.original_filename
    out["doc_type"] = (
        document.doc_type if isinstance(document.doc_type, str) else document.doc_type.value
    )
    out["saved_mappings"] = [mapping_out(m) for m in saved]
    return out


@router.post("/documents/versions/{version_id}/parse")
def parse_version(
    version_id: int,
    payload: ApplyMapping,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Re-reads the stored file with an explicit mapping and replaces the rows
    previously parsed from this version."""
    require_ca(user)
    version, document, case = _version_or_403(db, user, version_id)
    source = DOC_SOURCE.get(DocumentType(document.doc_type))
    if source is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This document holds no invoice rows")

    if payload.mapping_id:
        saved = db.get(ColumnMapping, payload.mapping_id)
        if not saved or saved.client_id != case.client_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Mapping not found for this client")
        spec = {
            "sheet_name": saved.sheet_name,
            "header_row": saved.header_row,
            "first_data_row": saved.first_data_row,
            "columns": saved.columns,
        }
    elif payload.mapping:
        spec = payload.mapping.model_dump()
    else:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Provide a mapping or a mapping_id")

    data = get_storage().read(version.storage_key)
    result = parser.parse_with_mapping(data, spec)

    # This version's rows are replaced, never duplicated, so re-mapping is safe
    # to repeat until it looks right.
    for row in db.execute(
        select(InvoiceRecord).where(InvoiceRecord.document_version_id == version.id)
    ).scalars().all():
        db.delete(row)
    db.flush()

    for rec in result["records"]:
        db.add(
            InvoiceRecord(
                case_id=case.id, source=source, document_version_id=version.id, **rec
            )
        )

    saved_out = None
    if payload.save_as and result["records"]:
        fingerprint = None
        if spec.get("header_row"):
            try:
                preview = parser.preview_workbook(data)
                sheet = next(
                    (s for s in preview["sheets"] if s["name"] == (spec.get("sheet_name") or s["name"])),
                    None,
                )
                if sheet and len(sheet["rows"]) >= spec["header_row"]:
                    fingerprint = parser.header_fingerprint(sheet["rows"][spec["header_row"] - 1])
            except Exception:
                fingerprint = None
        existing = db.execute(
            select(ColumnMapping).where(
                ColumnMapping.client_id == case.client_id,
                ColumnMapping.doc_type == document.doc_type,
                ColumnMapping.label == payload.save_as,
            )
        ).scalars().first()
        row = existing or ColumnMapping(
            client_id=case.client_id,
            doc_type=document.doc_type,
            label=payload.save_as,
            created_by_user_id=user.id,
        )
        row.sheet_name = spec.get("sheet_name")
        row.header_row = spec.get("header_row")
        row.first_data_row = spec.get("first_data_row") or 1
        row.columns = spec.get("columns") or {}
        row.fingerprint = fingerprint
        db.add(row)
        db.flush()
        saved_out = mapping_out(row)

    audit.record(
        db, user, AuditAction.UPDATE, "DocumentVersion",
        f"{document.title} v{version.version_no} parsed with a stated column mapping: "
        f"{len(result['records'])} rows",
        target_id=version.id, client_id=case.client_id, case_id=case.id,
        meta={"columns": spec.get("columns"), "errors": len(result["errors"])},
    )
    db.commit()
    return {
        "records": len(result["records"]),
        "errors": result["errors"],
        "warnings": result.get("warnings", []),
        "saved_mapping": saved_out,
    }


@router.get("/clients/{client_id}/column-mappings")
def list_mappings(
    client_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    require_ca(user)
    assert_client_access(db, user, client_id)
    rows = db.execute(
        select(ColumnMapping).where(ColumnMapping.client_id == client_id)
    ).scalars().all()
    return [mapping_out(m) for m in rows]


@router.delete("/column-mappings/{mapping_id}", status_code=204)
def delete_mapping(
    mapping_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    require_ca(user)
    row = db.get(ColumnMapping, mapping_id)
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Mapping not found")
    assert_client_access(db, user, row.client_id)
    db.delete(row)
    db.commit()
