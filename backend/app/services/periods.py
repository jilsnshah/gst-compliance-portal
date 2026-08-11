from __future__ import annotations

import calendar
from datetime import date
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import INITIAL_STATUS, CaseStatus, ReturnType
from app.models import ComplianceCase, Entity, FinancialYear, GSTRegistration, ReturnItem, TaxPeriod

MONTH_NAMES = list(calendar.month_name)  # index 1..12


def fy_code_for(year: int, month: int) -> str:
    """Indian FY runs April-March. July 2026 -> '2026-27'."""
    start = year if month >= 4 else year - 1
    return "{}-{}".format(start, str(start + 1)[2:])


def get_or_create_financial_year(db: Session, year: int, month: int) -> FinancialYear:
    code = fy_code_for(year, month)
    fy = db.execute(select(FinancialYear).where(FinancialYear.code == code)).scalars().first()
    if fy:
        return fy
    start_year = int(code.split("-")[0])
    fy = FinancialYear(
        code=code,
        start_date=date(start_year, 4, 1),
        end_date=date(start_year + 1, 3, 31),
    )
    db.add(fy)
    db.flush()
    return fy


def _next_month(year: int, month: int):
    return (year + 1, 1) if month == 12 else (year, month + 1)


def get_or_create_tax_period(db: Session, year: int, month: int) -> TaxPeriod:
    if not 1 <= month <= 12:
        raise ValueError("month must be 1-12")
    period = db.execute(
        select(TaxPeriod).where(TaxPeriod.year == year, TaxPeriod.month == month)
    ).scalars().first()
    if period:
        return period

    fy = get_or_create_financial_year(db, year, month)
    ny, nm = _next_month(year, month)
    period = TaxPeriod(
        financial_year_id=fy.id,
        year=year,
        month=month,
        code="{}-{:02d}".format(year, month),
        label="{} {}".format(MONTH_NAMES[month], year),
        # Statutory defaults. A real due-date engine is out of Stage 1 scope.
        gstr1_due_date=date(ny, nm, 11),
        gstr3b_due_date=date(ny, nm, 20),
    )
    db.add(period)
    db.flush()
    return period


def get_or_create_case(
    db: Session,
    gst_registration_id: int,
    year: int,
    month: int,
    assigned_employee_id: Optional[int] = None,
) -> ComplianceCase:
    """Opens a month for a GSTIN and creates its three return tracks."""
    period = get_or_create_tax_period(db, year, month)
    case = db.execute(
        select(ComplianceCase).where(
            ComplianceCase.gst_registration_id == gst_registration_id,
            ComplianceCase.tax_period_id == period.id,
        )
    ).scalars().first()
    if case:
        return case

    reg = db.get(GSTRegistration, gst_registration_id)
    entity = db.get(Entity, reg.entity_id)
    case = ComplianceCase(
        gst_registration_id=gst_registration_id,
        tax_period_id=period.id,
        client_id=entity.client_id,
        entity_id=entity.id,
        status=CaseStatus.IN_PROGRESS,
    )
    db.add(case)
    db.flush()

    owner = assigned_employee_id or reg.assigned_employee_id
    due = {
        ReturnType.GSTR1: period.gstr1_due_date,
        ReturnType.PR_RECON: period.gstr3b_due_date,
        ReturnType.GSTR3B: period.gstr3b_due_date,
    }
    for rt in (ReturnType.GSTR1, ReturnType.PR_RECON, ReturnType.GSTR3B):
        db.add(
            ReturnItem(
                case_id=case.id,
                return_type=rt,
                status=INITIAL_STATUS[rt.value],
                assigned_employee_id=owner,
                due_date=due[rt],
            )
        )
    db.flush()
    return case
