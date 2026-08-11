from __future__ import annotations

from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import Role
from app.models import (
    Client,
    ClientAssignment,
    ClientUser,
    ComplianceCase,
    Document,
    Entity,
    ReturnItem,
    User,
)


def visible_client_ids(db: Session, user: User) -> Optional[list]:
    """Client ids the user may see. None means 'no restriction' (CA_ADMIN)."""
    if user.role == Role.CA_ADMIN:
        return None
    if user.role == Role.CA_EMPLOYEE:
        if not user.employee:
            return []
        rows = db.execute(
            select(ClientAssignment.client_id).where(
                ClientAssignment.employee_id == user.employee.id
            )
        ).scalars()
        return list(rows)
    rows = db.execute(select(ClientUser.client_id).where(ClientUser.user_id == user.id)).scalars()
    return list(rows)


def scope_clients(db: Session, user: User, stmt):
    ids = visible_client_ids(db, user)
    if ids is None:
        return stmt
    return stmt.where(Client.id.in_(ids or [-1]))


def scope_by_client_column(db: Session, user: User, stmt, column):
    ids = visible_client_ids(db, user)
    if ids is None:
        return stmt
    return stmt.where(column.in_(ids or [-1]))


def assert_client_access(db: Session, user: User, client_id: int) -> None:
    ids = visible_client_ids(db, user)
    if ids is None or client_id in ids:
        return
    raise HTTPException(status.HTTP_403_FORBIDDEN, "No access to this client")


def get_case_or_403(db: Session, user: User, case_id: int) -> ComplianceCase:
    case = db.get(ComplianceCase, case_id)
    if not case:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Compliance case not found")
    assert_client_access(db, user, case.client_id)
    return case


def get_return_item_or_403(db: Session, user: User, return_item_id: int) -> ReturnItem:
    item = db.get(ReturnItem, return_item_id)
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Return item not found")
    assert_client_access(db, user, item.case.client_id)
    return item


def get_document_or_403(db: Session, user: User, document_id: int) -> Document:
    doc = db.get(Document, document_id)
    if not doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    case = db.get(ComplianceCase, doc.case_id)
    assert_client_access(db, user, case.client_id)
    return doc


def get_entity_or_403(db: Session, user: User, entity_id: int) -> Entity:
    entity = db.get(Entity, entity_id)
    if not entity:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found")
    assert_client_access(db, user, entity.client_id)
    return entity


def require_ca(user: User) -> None:
    if user.role not in (Role.CA_EMPLOYEE, Role.CA_ADMIN):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "CA staff only")


def require_admin(user: User) -> None:
    if user.role != Role.CA_ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin only")
