from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.types import Email

from app.core.enums import (
    Constitution,
    DocumentType,
    FilingFrequency,
    MismatchResolution,
    ReturnStatus,
    Role,
)


class LoginRequest(BaseModel):
    email: Email
    password: str


class ClientCreate(BaseModel):
    """A client and its single login, created together by an admin."""

    name: str
    email: Email
    password: str
    phone: Optional[str] = None


class EntityCreate(BaseModel):
    client_id: int
    file_number: str
    legal_name: str
    trade_name: Optional[str] = None
    pan: str = Field(min_length=10, max_length=10)
    constitution: Constitution = Constitution.OTHER
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    contact_person: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[Email] = None
    applicable_services: list = []
    gstin: str = Field(min_length=15, max_length=15)
    state_code: Optional[str] = None
    state_name: Optional[str] = None
    registration_date: Optional[date] = None
    filing_frequency: FilingFrequency = FilingFrequency.MONTHLY
    assigned_employee_id: Optional[int] = None


class UserCreate(BaseModel):
    email: Email
    full_name: str
    password: str
    role: Role
    phone: Optional[str] = None
    employee_code: Optional[str] = None
    designation: Optional[str] = None
    client_id: Optional[int] = None  # required for CLIENT role


class AssignmentCreate(BaseModel):
    client_id: int
    employee_id: int
    note: Optional[str] = None


class CaseCreate(BaseModel):
    entity_id: int
    year: int
    month: int = Field(ge=1, le=12)


class TransitionRequest(BaseModel):
    to_status: ReturnStatus
    note: Optional[str] = None
    override: bool = False


class AssignRequest(BaseModel):
    assigned_employee_id: Optional[int] = None
    due_date: Optional[date] = None
    priority: Optional[int] = None


class QueryCreate(BaseModel):
    return_item_id: int
    title: str
    body: Optional[str] = None
    document_version_id: Optional[int] = None
    invoice_match_id: Optional[int] = None
    requires_revision: bool = False


class QueryAnswer(BaseModel):
    body: str


class ConversationCreate(BaseModel):
    subject: str
    case_id: Optional[int] = None
    return_item_id: Optional[int] = None
    document_id: Optional[int] = None
    invoice_match_id: Optional[int] = None
    client_id: Optional[int] = None


class MessageCreate(BaseModel):
    body: str
    is_internal_note: bool = False
    document_version_ids: list = []


class DocumentVersionReview(BaseModel):
    verified: bool
    remarks: Optional[str] = None


class ReconRunRequest(BaseModel):
    amount_tolerance: float = 1.0
    date_tolerance_days: int = 15


class MismatchUpdate(BaseModel):
    resolution_status: Optional[MismatchResolution] = None
    ca_remark: Optional[str] = None
    client_response: Optional[str] = None
    resolution_note: Optional[str] = None
    assigned_employee_id: Optional[int] = None


class PaymentConfirm(BaseModel):
    """The client saying they have paid. Everything here is optional -- the
    confirmation itself is the fact that matters."""

    reference: Optional[str] = None
    note: Optional[str] = None

class FilingRecord(BaseModel):
    arn: Optional[str] = None
    filed_on: Optional[date] = None
    portal_reference: Optional[str] = None


class UploadMeta(BaseModel):
    doc_type: DocumentType
    return_item_id: Optional[int] = None
    on_behalf_of_client: bool = False
    remarks: Optional[str] = None
