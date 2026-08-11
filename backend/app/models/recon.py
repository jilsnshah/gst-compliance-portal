from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import JSON, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.core.enums import InvoiceSource, MatchStatus, MismatchResolution


class ReconciliationRun(Base):
    """One execution of the matching engine for a case. Re-running supersedes
    the previous run but never deletes it."""

    __tablename__ = "reconciliation_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("compliance_cases.id"), index=True)
    return_item_id: Mapped[int] = mapped_column(ForeignKey("return_items.id"), index=True)
    gstr2b_version_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("document_versions.id"), nullable=True
    )
    pr_version_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("document_versions.id"), nullable=True
    )

    run_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    is_superseded: Mapped[bool] = mapped_column(default=False, index=True)
    params: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    summary: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    matches: Mapped[list["InvoiceMatch"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class InvoiceRecord(Base):
    """A single invoice line parsed from either GSTR-2B or the Purchase
    Register. Both sources share one table so matching is a self-join."""

    __tablename__ = "invoice_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("compliance_cases.id"), index=True)
    source: Mapped[InvoiceSource] = mapped_column(String(20), index=True)
    document_version_id: Mapped[int] = mapped_column(ForeignKey("document_versions.id"), index=True)

    supplier_gstin: Mapped[Optional[str]] = mapped_column(String(15), index=True)
    supplier_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    invoice_no: Mapped[Optional[str]] = mapped_column(String(50))
    # Upper-cased, punctuation stripped, leading zeros dropped -- the join key.
    invoice_no_normalized: Mapped[Optional[str]] = mapped_column(String(50), index=True)
    invoice_date: Mapped[Optional[date]] = mapped_column(Date)
    invoice_type: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    place_of_supply: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    taxable_value: Mapped[float] = mapped_column(Float, default=0.0)
    igst: Mapped[float] = mapped_column(Float, default=0.0)
    cgst: Mapped[float] = mapped_column(Float, default=0.0)
    sgst: Mapped[float] = mapped_column(Float, default=0.0)
    cess: Mapped[float] = mapped_column(Float, default=0.0)
    total_value: Mapped[float] = mapped_column(Float, default=0.0)

    itc_available: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)  # 2B only
    source_row_no: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    raw: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    @property
    def total_tax(self) -> float:
        return round((self.igst or 0) + (self.cgst or 0) + (self.sgst or 0) + (self.cess or 0), 2)


class InvoiceMatch(Base):
    """Result row of the matching engine, and the unit of the mismatch
    workflow: it carries its own status, owner, remarks and resolution."""

    __tablename__ = "invoice_matches"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("compliance_cases.id"), index=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("reconciliation_runs.id"), index=True)

    pr_record_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("invoice_records.id"), nullable=True
    )
    gstr2b_record_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("invoice_records.id"), nullable=True
    )

    match_status: Mapped[MatchStatus] = mapped_column(String(30), index=True)
    diff_flags: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    taxable_value_diff: Mapped[float] = mapped_column(Float, default=0.0)
    tax_diff: Mapped[float] = mapped_column(Float, default=0.0)
    match_score: Mapped[float] = mapped_column(Float, default=0.0)

    resolution_status: Mapped[MismatchResolution] = mapped_column(
        String(30), default=MismatchResolution.OPEN, index=True
    )
    assigned_employee_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("employees.id"), nullable=True, index=True
    )
    ca_remark: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    client_response: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resolution_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resolved_by_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    run: Mapped[ReconciliationRun] = relationship(back_populates="matches")
    pr_record: Mapped[Optional[InvoiceRecord]] = relationship(foreign_keys=[pr_record_id])
    gstr2b_record: Mapped[Optional[InvoiceRecord]] = relationship(foreign_keys=[gstr2b_record_id])
