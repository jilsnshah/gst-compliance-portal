from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.core.enums import NotificationType


class Conversation(Base):
    """A thread anchored to a point in the compliance hierarchy. Nullable FKs
    rather than a generic (type, id) pair so the anchors stay queryable."""

    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True)
    case_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("compliance_cases.id"), nullable=True, index=True
    )
    return_item_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("return_items.id"), nullable=True, index=True
    )
    document_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("documents.id"), nullable=True, index=True
    )
    invoice_match_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("invoice_matches.id"), nullable=True, index=True
    )

    subject: Mapped[str] = mapped_column(String(255))
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_message_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="Message.created_at"
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), index=True)
    author_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)
    # Internal notes are visible to CA staff only, never to the client.
    is_internal_note: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")
    attachments: Mapped[list["MessageAttachment"]] = relationship(
        back_populates="message", cascade="all, delete-orphan"
    )


class MessageAttachment(Base):
    __tablename__ = "message_attachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("messages.id"), index=True)
    document_version_id: Mapped[int] = mapped_column(ForeignKey("document_versions.id"))

    message: Mapped[Message] = relationship(back_populates="attachments")
    version: Mapped["DocumentVersion"] = relationship("DocumentVersion", lazy="joined")


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    notification_type: Mapped[NotificationType] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    case_id: Mapped[Optional[int]] = mapped_column(ForeignKey("compliance_cases.id"), nullable=True)
    return_item_id: Mapped[Optional[int]] = mapped_column(ForeignKey("return_items.id"), nullable=True)
    conversation_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("conversations.id"), nullable=True
    )

    is_read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
