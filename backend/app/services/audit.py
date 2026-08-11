from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.core.enums import AuditAction
from app.models import AuditLog, User


def record(
    db: Session,
    actor: Optional[User],
    action: AuditAction,
    target_type: str,
    description: str,
    target_id: Optional[int] = None,
    client_id: Optional[int] = None,
    case_id: Optional[int] = None,
    meta: Optional[dict] = None,
) -> AuditLog:
    """Single entry point for the audit trail. Does not commit -- the caller's
    transaction owns it, so an audit row can never survive a rolled-back action."""
    log = AuditLog(
        actor_user_id=actor.id if actor else None,
        actor_name=actor.full_name if actor else "system",
        actor_role=actor.role if actor else None,
        action=action,
        target_type=target_type,
        target_id=target_id,
        client_id=client_id,
        case_id=case_id,
        description=description,
        meta=meta or {},
    )
    db.add(log)
    return log
