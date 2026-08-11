from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import ReturnType
from app.models import ComplianceCase, GSTR3BPayment, ReturnItem, User


def get_or_create_payment(
    db: Session, case: ComplianceCase, user: Optional[User] = None
) -> GSTR3BPayment:
    item = db.execute(
        select(ReturnItem).where(
            ReturnItem.case_id == case.id, ReturnItem.return_type == ReturnType.GSTR3B
        )
    ).scalars().first()
    row = db.execute(
        select(GSTR3BPayment).where(GSTR3BPayment.return_item_id == item.id)
    ).scalars().first()
    if row:
        return row
    row = GSTR3BPayment(case_id=case.id, return_item_id=item.id)
    db.add(row)
    db.flush()
    return row
