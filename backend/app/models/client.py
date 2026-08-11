from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.core.enums import Constitution, FilingFrequency


class Client(Base):
    """Top-level customer of the CA firm. Not the lowest-level object --
    entities (files) and GST registrations sit below it."""

    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_code: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    primary_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    primary_phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    entities: Mapped[list["Entity"]] = relationship(back_populates="client")
    user_links: Mapped[list["ClientUser"]] = relationship(back_populates="client")
    assignments: Mapped[list["ClientAssignment"]] = relationship(back_populates="client")


class Entity(Base):
    """A file / business belonging to a client. Holds PAN-level master data."""

    __tablename__ = "entities"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True)

    file_number: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    legal_name: Mapped[str] = mapped_column(String(255))
    trade_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    pan: Mapped[str] = mapped_column(String(10), index=True)
    constitution: Mapped[Constitution] = mapped_column(String(30), default=Constitution.OTHER)

    address_line1: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    address_line2: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    state: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    pincode: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)

    contact_person: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    contact_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    applicable_services: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    client: Mapped[Client] = relationship(back_populates="entities")
    registrations: Mapped[list["GSTRegistration"]] = relationship(back_populates="entity")


class GSTRegistration(Base):
    """A GSTIN. The critical identifier for everything downstream -- compliance
    cases hang off this, not off the file number."""

    __tablename__ = "gst_registrations"

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id"), index=True)

    gstin: Mapped[str] = mapped_column(String(15), unique=True, index=True)
    state_code: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)
    state_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    registration_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    filing_frequency: Mapped[FilingFrequency] = mapped_column(
        String(20), default=FilingFrequency.MONTHLY
    )

    # Team member responsible for this GSTIN's compliance.
    assigned_employee_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("employees.id"), nullable=True, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    entity: Mapped[Entity] = relationship(back_populates="registrations")


class ClientAssignment(Base):
    """Which CA employees may see which clients. CA_ADMIN bypasses this."""

    __tablename__ = "client_assignments"
    __table_args__ = (UniqueConstraint("client_id", "employee_id", name="uq_client_assignment"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    note: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    client: Mapped[Client] = relationship(back_populates="assignments")
