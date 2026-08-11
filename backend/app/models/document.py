from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.core.enums import DocumentType, DocumentVersionStatus


class Document(Base):
    """A logical document slot (e.g. 'GSTR-1 data for July 2026'). Files are
    never overwritten -- each upload creates a new DocumentVersion."""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("compliance_cases.id"), index=True)
    return_item_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("return_items.id"), nullable=True, index=True
    )
    doc_type: Mapped[DocumentType] = mapped_column(String(30), index=True)
    title: Mapped[str] = mapped_column(String(255))
    current_version_no: Mapped[int] = mapped_column(Integer, default=0)

    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    versions: Mapped[list["DocumentVersion"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="DocumentVersion.version_no"
    )


class DocumentVersion(Base):
    __tablename__ = "document_versions"
    __table_args__ = (UniqueConstraint("document_id", "version_no", name="uq_doc_version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    version_no: Mapped[int] = mapped_column(Integer)

    original_filename: Mapped[str] = mapped_column(String(255))
    storage_key: Mapped[str] = mapped_column(String(512))
    content_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    checksum: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    uploaded_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    # True when CA staff uploaded this on the client's behalf.
    uploaded_on_behalf_of_client: Mapped[bool] = mapped_column(Boolean, default=False)

    status: Mapped[DocumentVersionStatus] = mapped_column(
        String(30), default=DocumentVersionStatus.PENDING_REVIEW
    )
    remarks: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    document: Mapped[Document] = relationship(back_populates="versions")
    # Eager-loaded so listings can show "who has the latest" without an N+1.
    uploader: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[uploaded_by_user_id], lazy="joined"
    )
