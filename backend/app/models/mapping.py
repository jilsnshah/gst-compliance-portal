from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.enums import DocumentType


class ColumnMapping(Base):
    """How one client's workbook lays out its columns.

    Client purchase registers come out of whatever accounting software they
    use: arbitrary column names, arbitrary order, sometimes no header row at
    all. Guessing from column names cannot be made reliable, so the CA states
    the mapping once and it is reused every month -- columns are addressed by
    position, never by name.
    """

    __tablename__ = "column_mappings"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True)
    doc_type: Mapped[DocumentType] = mapped_column(String(30), index=True)
    label: Mapped[str] = mapped_column(String(120))

    sheet_name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    # 1-based, as the CA sees them in Excel. header_row may be null when the
    # file has no header at all.
    header_row: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    first_data_row: Mapped[int] = mapped_column(Integer, default=2)

    # {"supplier_gstin": 0, "invoice_no": 3, ...} -- values are 0-based column
    # indexes, so an unnamed column is addressed just as well as a named one.
    columns: Mapped[dict] = mapped_column(JSON, default=dict)

    # Hash of the normalised header row. Lets a saved mapping be recognised
    # automatically next month, and lets a changed export format be detected
    # instead of silently mis-parsed.
    fingerprint: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)

    is_default: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
