from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.enums import AuditAction


class AuditLog(Base):
    """Append-only. Written by app.services.audit.record() from every state
    mutation -- nothing else should insert here."""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    actor_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    actor_role: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    action: Mapped[AuditAction] = mapped_column(String(30), index=True)
    target_type: Mapped[str] = mapped_column(String(50), index=True)
    target_id: Mapped[Optional[int]] = mapped_column(nullable=True, index=True)

    client_id: Mapped[Optional[int]] = mapped_column(ForeignKey("clients.id"), nullable=True, index=True)
    case_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("compliance_cases.id"), nullable=True, index=True
    )

    description: Mapped[str] = mapped_column(Text)
    meta: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
