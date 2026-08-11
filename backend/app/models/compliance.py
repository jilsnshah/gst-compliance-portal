from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.core.enums import CaseStatus, QueryStatus, ReturnStatus, ReturnType


class FinancialYear(Base):
    __tablename__ = "financial_years"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(10), unique=True, index=True)  # 2026-27
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)

    periods: Mapped[list["TaxPeriod"]] = relationship(back_populates="financial_year")


class TaxPeriod(Base):
    """One filing month. Due dates live here so a Stage-2 due-date engine has
    somewhere to write."""

    __tablename__ = "tax_periods"
    __table_args__ = (UniqueConstraint("year", "month", name="uq_tax_period"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    financial_year_id: Mapped[int] = mapped_column(ForeignKey("financial_years.id"), index=True)
    year: Mapped[int] = mapped_column(Integer)
    month: Mapped[int] = mapped_column(Integer)  # 1-12
    code: Mapped[str] = mapped_column(String(7), index=True)  # 2026-07
    label: Mapped[str] = mapped_column(String(30))  # July 2026
    gstr1_due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    gstr3b_due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    financial_year: Mapped[FinancialYear] = relationship(back_populates="periods")


class ComplianceCase(Base):
    """The spine of the system: one GSTIN x one tax period. Every document,
    query, conversation, invoice and filing for that month hangs off it."""

    __tablename__ = "compliance_cases"
    __table_args__ = (
        UniqueConstraint("entity_id", "tax_period_id", name="uq_case_entity_period"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id"), index=True)
    tax_period_id: Mapped[int] = mapped_column(ForeignKey("tax_periods.id"), index=True)

    # Denormalised for cheap dashboard scoping. Kept in sync at creation time.
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True)

    status: Mapped[CaseStatus] = mapped_column(String(20), default=CaseStatus.NOT_STARTED, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    tax_period: Mapped[TaxPeriod] = relationship()
    return_items: Mapped[list["ReturnItem"]] = relationship(
        back_populates="case", cascade="all, delete-orphan"
    )


class ReturnItem(Base):
    """A single workflow track inside a case: GSTR-1, PR reconciliation or
    GSTR-3B. All three use the same document/query/status machinery."""

    __tablename__ = "return_items"
    __table_args__ = (UniqueConstraint("case_id", "return_type", name="uq_case_return_type"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("compliance_cases.id"), index=True)
    return_type: Mapped[ReturnType] = mapped_column(String(20), index=True)
    status: Mapped[ReturnStatus] = mapped_column(
        String(30), default=ReturnStatus.AWAITING_CLIENT_DATA, index=True
    )

    assigned_employee_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("employees.id"), nullable=True, index=True
    )
    due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, index=True)
    priority: Mapped[int] = mapped_column(Integer, default=0)  # higher = more urgent
    internal_remarks: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # assigned_employee_id is who *should* handle this (defaulted from the
    # GSTIN); these record who actually picked it up and when.
    review_started_by_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    review_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # True once a human has deliberately assigned this item, which stops the
    # reviewer-claim from silently reassigning it later.
    assignment_is_explicit: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    case: Mapped[ComplianceCase] = relationship(back_populates="return_items")
    transitions: Mapped[list["StatusTransition"]] = relationship(back_populates="return_item")
    reviewer: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[review_started_by_user_id], lazy="joined"
    )


class StatusTransition(Base):
    """Immutable record of every workflow hop. Feeds the audit trail view."""

    __tablename__ = "status_transitions"

    id: Mapped[int] = mapped_column(primary_key=True)
    return_item_id: Mapped[int] = mapped_column(ForeignKey("return_items.id"), index=True)
    from_status: Mapped[Optional[ReturnStatus]] = mapped_column(String(30), nullable=True)
    to_status: Mapped[ReturnStatus] = mapped_column(String(30))
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    return_item: Mapped[ReturnItem] = relationship(back_populates="transitions")


class Query(Base):
    """A CA question that blocks progress until the client answers. Anchored to
    a return item, and optionally to a document version or an invoice match."""

    __tablename__ = "queries"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("compliance_cases.id"), index=True)
    return_item_id: Mapped[int] = mapped_column(ForeignKey("return_items.id"), index=True)
    document_version_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("document_versions.id"), nullable=True
    )
    invoice_match_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("invoice_matches.id"), nullable=True, index=True
    )
    conversation_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("conversations.id"), nullable=True
    )

    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[QueryStatus] = mapped_column(String(20), default=QueryStatus.OPEN, index=True)
    requires_revision: Mapped[bool] = mapped_column(default=False)

    raised_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    resolved_by_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    answered_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
