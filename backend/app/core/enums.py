from __future__ import annotations

from enum import Enum


class Role(str, Enum):
    CLIENT = "CLIENT"
    CA_EMPLOYEE = "CA_EMPLOYEE"
    CA_ADMIN = "CA_ADMIN"


CA_ROLES = {Role.CA_EMPLOYEE, Role.CA_ADMIN}


class FilingFrequency(str, Enum):
    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"


class Constitution(str, Enum):
    PROPRIETORSHIP = "PROPRIETORSHIP"
    PARTNERSHIP = "PARTNERSHIP"
    LLP = "LLP"
    PRIVATE_LIMITED = "PRIVATE_LIMITED"
    PUBLIC_LIMITED = "PUBLIC_LIMITED"
    HUF = "HUF"
    TRUST = "TRUST"
    OTHER = "OTHER"


class ReturnType(str, Enum):
    GSTR1 = "GSTR1"
    PR_RECON = "PR_RECON"  # GSTR-2B <-> Purchase Register reconciliation
    GSTR3B = "GSTR3B"


RETURN_LABELS = {
    ReturnType.GSTR1: "GSTR-1",
    ReturnType.PR_RECON: "GSTR-2B Reconciliation",
    ReturnType.GSTR3B: "GSTR-3B",
}


class ReturnStatus(str, Enum):
    """Six states, total.

    The query/revision/resubmit loop is deliberately absent: all of that happens
    inside UNDER_CA_REVIEW through the discussion and new document versions, and
    never moves the status. "Who are we waiting on" is derived from whether an
    unanswered query exists, not stored as a state.
    """

    AWAITING_CLIENT_DATA = "AWAITING_CLIENT_DATA"
    CLIENT_DATA_SUBMITTED = "CLIENT_DATA_SUBMITTED"
    UNDER_CA_REVIEW = "UNDER_CA_REVIEW"
    AWAITING_PAYMENT = "AWAITING_PAYMENT"  # GSTR-3B only
    VERIFIED = "VERIFIED"
    FILED = "FILED"


# Which states each track can occupy, and where each one ends. The purchase
# reconciliation is never filed, so it finishes at VERIFIED.
TRACK_STATES = {
    "GSTR1": [
        ReturnStatus.AWAITING_CLIENT_DATA,
        ReturnStatus.CLIENT_DATA_SUBMITTED,
        ReturnStatus.UNDER_CA_REVIEW,
        ReturnStatus.VERIFIED,
        ReturnStatus.FILED,
    ],
    "PR_RECON": [
        ReturnStatus.AWAITING_CLIENT_DATA,
        ReturnStatus.CLIENT_DATA_SUBMITTED,
        ReturnStatus.UNDER_CA_REVIEW,
        ReturnStatus.VERIFIED,
    ],
    "GSTR3B": [
        ReturnStatus.UNDER_CA_REVIEW,
        ReturnStatus.AWAITING_PAYMENT,
        ReturnStatus.VERIFIED,
        ReturnStatus.FILED,
    ],
}

INITIAL_STATUS = {
    "GSTR1": ReturnStatus.AWAITING_CLIENT_DATA,
    "PR_RECON": ReturnStatus.AWAITING_CLIENT_DATA,
    # GSTR-3B needs no client upload -- the CA starts from the portal figures.
    "GSTR3B": ReturnStatus.UNDER_CA_REVIEW,
}

TERMINAL_STATUS = {
    "GSTR1": ReturnStatus.FILED,
    "PR_RECON": ReturnStatus.VERIFIED,
    "GSTR3B": ReturnStatus.FILED,
}


def track_key(return_type) -> str:
    return return_type.value if hasattr(return_type, "value") else str(return_type)


def is_terminal(return_type, status) -> bool:
    return ReturnStatus(status) == TERMINAL_STATUS[track_key(return_type)]


class ClientVisibleStatus(str, Enum):
    """Three states. The only question a client's status answers is whether
    they have to do something."""

    ACTION_NEEDED = "ACTION_NEEDED"
    WITH_CA = "WITH_CA"
    DONE = "DONE"


CLIENT_STATUS_MAP = {
    ReturnStatus.AWAITING_CLIENT_DATA: ClientVisibleStatus.ACTION_NEEDED,
    ReturnStatus.CLIENT_DATA_SUBMITTED: ClientVisibleStatus.WITH_CA,
    # Flips to ACTION_NEEDED when an unanswered query is sitting with the client.
    ReturnStatus.UNDER_CA_REVIEW: ClientVisibleStatus.WITH_CA,
    ReturnStatus.AWAITING_PAYMENT: ClientVisibleStatus.ACTION_NEEDED,
    # DONE instead when VERIFIED is the track's terminal state (reconciliation).
    ReturnStatus.VERIFIED: ClientVisibleStatus.WITH_CA,
    ReturnStatus.FILED: ClientVisibleStatus.DONE,
}

CLIENT_STATUS_LABELS = {
    ClientVisibleStatus.ACTION_NEEDED: "Your turn",
    ClientVisibleStatus.WITH_CA: "With your CA team",
    ClientVisibleStatus.DONE: "Done",
}


def client_status_for(return_type, status, waiting_on_client: bool = False) -> ClientVisibleStatus:
    status = ReturnStatus(status)
    if is_terminal(return_type, status):
        return ClientVisibleStatus.DONE
    if status == ReturnStatus.UNDER_CA_REVIEW and waiting_on_client:
        return ClientVisibleStatus.ACTION_NEEDED
    return CLIENT_STATUS_MAP[status]


class CaseStatus(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"


class DocumentType(str, Enum):
    GSTR1_DATA = "GSTR1_DATA"
    PURCHASE_REGISTER = "PURCHASE_REGISTER"
    GSTR2B = "GSTR2B"
    CHALLAN = "CHALLAN"
    PAYMENT_PROOF = "PAYMENT_PROOF"
    ACKNOWLEDGEMENT = "ACKNOWLEDGEMENT"
    MESSAGE_ATTACHMENT = "MESSAGE_ATTACHMENT"
    SUPPORTING = "SUPPORTING"
    OTHER = "OTHER"


# Who is normally expected to supply the document. CA staff may always upload
# on behalf of the client (uploaded_on_behalf_of flag).
CLIENT_SUPPLIED_DOCS = {
    DocumentType.GSTR1_DATA,
    DocumentType.PURCHASE_REGISTER,
    DocumentType.PAYMENT_PROOF,
    DocumentType.SUPPORTING,
}


class DocumentVersionStatus(str, Enum):
    # CA-supplied records (GSTR-2B, challan, acknowledgement) are never
    # "pending review" -- nobody is going to verify the firm's own download.
    NOT_APPLICABLE = "NOT_APPLICABLE"
    PENDING_REVIEW = "PENDING_REVIEW"
    UNDER_REVIEW = "UNDER_REVIEW"
    QUERY_RAISED = "QUERY_RAISED"
    SUPERSEDED = "SUPERSEDED"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"


# Only the client's own data goes through a verify/reject cycle.
REVIEWABLE_DOCS = {
    DocumentType.GSTR1_DATA,
    DocumentType.PURCHASE_REGISTER,
}

# These have dedicated actions that also move the workflow, so they must not be
# posted through the generic upload endpoint.
DEDICATED_UPLOAD_DOCS = {
    DocumentType.CHALLAN,
    DocumentType.ACKNOWLEDGEMENT,
}


class QueryStatus(str, Enum):
    OPEN = "OPEN"
    ANSWERED = "ANSWERED"
    RESOLVED = "RESOLVED"


class InvoiceSource(str, Enum):
    GSTR2B = "GSTR2B"
    PURCHASE_REGISTER = "PURCHASE_REGISTER"
    # Outward supplies parsed from the client's GSTR-1 workbook. Used only to
    # derive system values for the GSTR-3B control sheet.
    GSTR1_SALES = "GSTR1_SALES"


class MatchStatus(str, Enum):
    EXACT_MATCH = "EXACT_MATCH"
    PARTIAL_MATCH = "PARTIAL_MATCH"
    PROBABLE_MATCH = "PROBABLE_MATCH"
    MISMATCH = "MISMATCH"
    MISSING_IN_2B = "MISSING_IN_2B"
    MISSING_IN_PR = "MISSING_IN_PR"


ACTIONABLE_MATCH_STATUSES = {
    MatchStatus.PARTIAL_MATCH,
    MatchStatus.PROBABLE_MATCH,
    MatchStatus.MISMATCH,
    MatchStatus.MISSING_IN_2B,
    MatchStatus.MISSING_IN_PR,
}


class MismatchResolution(str, Enum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    CLIENT_RESPONDED = "CLIENT_RESPONDED"
    RESOLVED = "RESOLVED"
    DEFERRED_NEXT_PERIOD = "DEFERRED_NEXT_PERIOD"
    WRITTEN_OFF = "WRITTEN_OFF"


class DiffFlag(str, Enum):
    GSTIN_MISMATCH = "GSTIN_MISMATCH"
    INVOICE_NO_MISMATCH = "INVOICE_NO_MISMATCH"
    INVOICE_DATE_MISMATCH = "INVOICE_DATE_MISMATCH"
    TAXABLE_VALUE_MISMATCH = "TAXABLE_VALUE_MISMATCH"
    TAX_AMOUNT_MISMATCH = "TAX_AMOUNT_MISMATCH"
    IGST_MISMATCH = "IGST_MISMATCH"
    CGST_MISMATCH = "CGST_MISMATCH"
    SGST_MISMATCH = "SGST_MISMATCH"
    CESS_MISMATCH = "CESS_MISMATCH"


class PaymentStatus(str, Enum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    CHALLAN_PENDING = "CHALLAN_PENDING"
    CHALLAN_ISSUED = "CHALLAN_ISSUED"
    PAYMENT_CONFIRMED = "PAYMENT_CONFIRMED"


class NotificationType(str, Enum):
    DOCUMENT_UPLOADED = "DOCUMENT_UPLOADED"
    QUERY_RAISED = "QUERY_RAISED"
    QUERY_ANSWERED = "QUERY_ANSWERED"
    STATUS_CHANGED = "STATUS_CHANGED"
    MESSAGE_POSTED = "MESSAGE_POSTED"
    CHALLAN_ISSUED = "CHALLAN_ISSUED"
    PAYMENT_CONFIRMED = "PAYMENT_CONFIRMED"
    ACKNOWLEDGEMENT_UPLOADED = "ACKNOWLEDGEMENT_UPLOADED"
    RECON_COMPLETED = "RECON_COMPLETED"


class AuditAction(str, Enum):
    LOGIN = "LOGIN"
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    UPLOAD = "UPLOAD"
    DOWNLOAD = "DOWNLOAD"
    STATUS_CHANGE = "STATUS_CHANGE"
    QUERY_RAISED = "QUERY_RAISED"
    QUERY_ANSWERED = "QUERY_ANSWERED"
    QUERY_RESOLVED = "QUERY_RESOLVED"
    MESSAGE_POSTED = "MESSAGE_POSTED"
    RECON_RUN = "RECON_RUN"
    MISMATCH_UPDATED = "MISMATCH_UPDATED"
    CHALLAN_ISSUED = "CHALLAN_ISSUED"
    PAYMENT_CONFIRMED = "PAYMENT_CONFIRMED"
    FILED = "FILED"
    ASSIGNED = "ASSIGNED"
    OVERRIDE = "OVERRIDE"
