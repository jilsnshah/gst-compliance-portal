from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import NotificationType, Role
from app.models import (
    ClientAssignment,
    ClientUser,
    ComplianceCase,
    Employee,
    Notification,
    ReturnItem,
    User,
)


def _add(db: Session, user_ids, ntype, title, body, case_id, return_item_id, conversation_id):
    for uid in set(user_ids):
        db.add(
            Notification(
                user_id=uid,
                notification_type=ntype,
                title=title,
                body=body,
                case_id=case_id,
                return_item_id=return_item_id,
                conversation_id=conversation_id,
            )
        )


def client_user_ids(db: Session, client_id: int) -> list:
    return list(
        db.execute(select(ClientUser.user_id).where(ClientUser.client_id == client_id)).scalars()
    )


def ca_user_ids(db: Session, client_id: int, return_item: Optional[ReturnItem] = None) -> list:
    """Assigned staff for the client, the return item's owner, plus all admins."""
    ids = list(
        db.execute(
            select(Employee.user_id)
            .join(ClientAssignment, ClientAssignment.employee_id == Employee.id)
            .where(ClientAssignment.client_id == client_id)
        ).scalars()
    )
    if return_item is not None and return_item.assigned_employee_id:
        emp = db.get(Employee, return_item.assigned_employee_id)
        if emp:
            ids.append(emp.user_id)
    ids += list(db.execute(select(User.id).where(User.role == Role.CA_ADMIN)).scalars())
    return ids


def notify(
    db: Session,
    ntype: NotificationType,
    title: str,
    body: str = "",
    case: Optional[ComplianceCase] = None,
    return_item: Optional[ReturnItem] = None,
    conversation_id: Optional[int] = None,
    client_id: Optional[int] = None,
    to_client: bool = False,
    to_ca: bool = False,
    exclude_user_id: Optional[int] = None,
) -> None:
    cid = client_id if client_id is not None else (case.client_id if case else None)
    if cid is None:
        return
    targets = []
    if to_client:
        targets += client_user_ids(db, cid)
    if to_ca:
        targets += ca_user_ids(db, cid, return_item)
    if exclude_user_id is not None:
        targets = [t for t in targets if t != exclude_user_id]
    _add(
        db,
        targets,
        ntype,
        title,
        body,
        case.id if case else None,
        return_item.id if return_item else None,
        conversation_id,
    )
