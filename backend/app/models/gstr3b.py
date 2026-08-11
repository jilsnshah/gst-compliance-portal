from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.enums import PaymentStatus


class GSTR3BPayment(Base):
    """Whether tax was payable this month, and the client's confirmation that
    they paid it.

    There is deliberately no control sheet here. The CA reads the figures on
    the GST portal and, if anything is payable, uploads the challan PDF -- that
    upload is the statement that tax is due, and this row only records what
    happened to it. No amounts are re-keyed into this system.
    """

    __tablename__ = "gstr3b_payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("compliance_cases.id"), index=True)
    return_item_id: Mapped[int] = mapped_column(ForeignKey("return_items.id"), unique=True)

    payment_status: Mapped[PaymentStatus] = mapped_column(
        String(30), default=PaymentStatus.NOT_APPLICABLE, index=True
    )
    confirmed_by_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    reference: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class Filing(Base):
    """Record of the return actually being filed on the GST portal, plus the
    acknowledgement stored against GSTIN + FY + period + return."""

    __tablename__ = "filings"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("compliance_cases.id"), index=True)
    return_item_id: Mapped[int] = mapped_column(ForeignKey("return_items.id"), unique=True)

    arn: Mapped[Optional[str]] = mapped_column(String(30), nullable=True, index=True)
    filed_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    portal_reference: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    acknowledgement_document_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("documents.id"), nullable=True
    )

    filed_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
