"""Import every model module so SQLAlchemy's registry can resolve the string
relationship targets and Base.metadata is complete."""

from app.models.audit import AuditLog
from app.models.client import Client, ClientAssignment, Entity, GSTRegistration
from app.models.comms import Conversation, Message, MessageAttachment, Notification
from app.models.compliance import (
    ComplianceCase,
    FinancialYear,
    Query,
    ReturnItem,
    StatusTransition,
    TaxPeriod,
)
from app.models.document import Document, DocumentVersion
from app.models.gstr3b import Filing, GSTR3BPayment
from app.models.identity import ClientUser, Employee, User
from app.models.recon import InvoiceMatch, InvoiceRecord, ReconciliationRun

__all__ = [
    "AuditLog",
    "Client",
    "ClientAssignment",
    "ClientUser",
    "ComplianceCase",
    "Conversation",
    "Document",
    "DocumentVersion",
    "Employee",
    "Entity",
    "Filing",
    "FinancialYear",
    "GSTR3BPayment",
    "GSTRegistration",
    "InvoiceMatch",
    "InvoiceRecord",
    "Message",
    "MessageAttachment",
    "Notification",
    "Query",
    "ReconciliationRun",
    "ReturnItem",
    "StatusTransition",
    "TaxPeriod",
    "User",
]
