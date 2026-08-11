"""Dev-stage seed: test accounts, one CA firm's worth of masters, an open
compliance month and sample workbooks to exercise the matching engine.

    python seed.py            # create if absent
    python seed.py --reset    # drop the DB file and rebuild
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

from openpyxl import Workbook
from sqlalchemy import select

from app.core.config import settings
from app.core.db import Base, SessionLocal, engine
from app.core.enums import Constitution, FilingFrequency, Role
from app.core.security import hash_password
from app.models import (
    Client,
    ClientAssignment,
    ClientUser,
    Employee,
    Entity,
    GSTRegistration,
    User,
)
from app.services import periods

PASSWORD = "test123"
SAMPLE_DIR = Path(settings.storage_root) / "samples"


def reset_db():
    db_path = settings.database_url.replace("sqlite:///", "")
    if Path(db_path).exists():
        Path(db_path).unlink()
        print(f"removed {db_path}")


def make_user(db, email, name, role, password=PASSWORD, phone=None):
    user = db.execute(select(User).where(User.email == email)).scalars().first()
    if user:
        return user
    user = User(
        email=email,
        full_name=name,
        phone=phone,
        hashed_password=hash_password(password),
        role=role,
    )
    db.add(user)
    db.flush()
    return user


def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if db.execute(select(User)).scalars().first():
            print("database already seeded; use --reset to rebuild")
            return

        admin = make_user(db, "admin@test.com", "Priya Nair (Partner)", Role.CA_ADMIN)
        staff = make_user(db, "staff@test.com", "Rahul Mehta", Role.CA_EMPLOYEE)
        client_user = make_user(db, "client@test.com", "Amit Shah", Role.CLIENT, phone="9876543210")
        client_user2 = make_user(db, "client2@test.com", "Neha Kulkarni", Role.CLIENT)

        admin_emp = Employee(user_id=admin.id, employee_code="EMP001", designation="Partner")
        staff_emp = Employee(user_id=staff.id, employee_code="EMP002", designation="Senior Associate")
        db.add_all([admin_emp, staff_emp])
        db.flush()

        abc = Client(
            client_code="CL001",
            name="ABC Enterprises",
            primary_email="client@test.com",
            primary_phone="9876543210",
        )
        xyz = Client(client_code="CL002", name="XYZ Traders", primary_email="client2@test.com")
        db.add_all([abc, xyz])
        db.flush()

        db.add_all([
            ClientUser(user_id=client_user.id, client_id=abc.id, is_primary_contact=True),
            ClientUser(user_id=client_user2.id, client_id=xyz.id, is_primary_contact=True),
            # Staff sees ABC only -- XYZ stays admin-visible to prove scoping.
            ClientAssignment(client_id=abc.id, employee_id=staff_emp.id, note="Primary handler"),
            ClientAssignment(client_id=abc.id, employee_id=admin_emp.id),
            ClientAssignment(client_id=xyz.id, employee_id=admin_emp.id),
        ])

        abc_entity = Entity(
            client_id=abc.id,
            file_number="F-001",
            legal_name="ABC Enterprises",
            trade_name="ABC Traders",
            pan="AAACA1234A",
            constitution=Constitution.PARTNERSHIP,
            address_line1="12, Ashram Road",
            city="Ahmedabad",
            state="Gujarat",
            pincode="380009",
            contact_person="Amit Shah",
            contact_phone="9876543210",
            contact_email="client@test.com",
            applicable_services=["GST", "Income Tax", "TDS"],
        )
        abc_entity2 = Entity(
            client_id=abc.id,
            file_number="F-002",
            legal_name="ABC Logistics LLP",
            trade_name="ABC Logistics",
            pan="AAACB5678B",
            constitution=Constitution.LLP,
            city="Surat",
            state="Gujarat",
            contact_person="Amit Shah",
            contact_email="client@test.com",
            applicable_services=["GST"],
        )
        xyz_entity = Entity(
            client_id=xyz.id,
            file_number="F-003",
            legal_name="XYZ Traders Private Limited",
            pan="AAACX9999X",
            constitution=Constitution.PRIVATE_LIMITED,
            city="Pune",
            state="Maharashtra",
            applicable_services=["GST"],
        )
        db.add_all([abc_entity, abc_entity2, xyz_entity])
        db.flush()

        regs = [
            GSTRegistration(
                entity_id=abc_entity.id, gstin="24AAACA1234A1ZQ", state_code="24",
                state_name="Gujarat", registration_date=date(2021, 4, 1),
                filing_frequency=FilingFrequency.MONTHLY, assigned_employee_id=staff_emp.id,
            ),
            GSTRegistration(
                entity_id=abc_entity.id, gstin="27AAACA1234A1ZM", state_code="27",
                state_name="Maharashtra", registration_date=date(2022, 7, 1),
                filing_frequency=FilingFrequency.MONTHLY, assigned_employee_id=staff_emp.id,
            ),
            GSTRegistration(
                entity_id=abc_entity2.id, gstin="24AAACB5678B1ZP", state_code="24",
                state_name="Gujarat", assigned_employee_id=staff_emp.id,
            ),
            GSTRegistration(
                entity_id=xyz_entity.id, gstin="27AAACX9999X1ZR", state_code="27",
                state_name="Maharashtra", assigned_employee_id=admin_emp.id,
            ),
        ]
        db.add_all(regs)
        db.flush()

        for reg in regs[:3]:
            for year, month in ((2026, 6), (2026, 7)):
                periods.get_or_create_case(db, reg.id, year, month)

        db.commit()
        print("seeded database at", settings.database_url)
        print("  admin@test.com   / test123   (CA_ADMIN)")
        print("  staff@test.com   / test123   (CA_EMPLOYEE, sees ABC only)")
        print("  client@test.com  / test123   (CLIENT, ABC Enterprises)")
        print("  client2@test.com / test123   (CLIENT, XYZ Traders)")
    finally:
        db.close()


# --------------------------------------------------- sample workbooks
PR_ROWS = [
    # gstin, name, invoice no, date, taxable, igst, cgst, sgst
    ("24AAAAA1111A1Z1", "Sharma Steel Traders", "INV-1001", date(2026, 7, 3), 150000, 0, 13500, 13500),
    ("24BBBBB2222B1Z2", "Patel Packaging",      "INV-1002", date(2026, 7, 5), 82000, 0, 7380, 7380),
    ("27CCCCC3333C1Z3", "Mumbai Freight Co",    "INV-1003", date(2026, 7, 8), 45000, 8100, 0, 0),
    ("24DDDDD4444D1Z4", "Gandhi Hardware",      "INV-1004", date(2026, 7, 11), 23500, 0, 2115, 2115),
    # Taxable value differs from 2B -> MISMATCH
    ("24EEEEE5555E1Z5", "Shah Chemicals",       "INV-1005", date(2026, 7, 14), 96000, 0, 8640, 8640),
    # Date differs from 2B -> PARTIAL_MATCH
    ("27FFFFF6666F1Z6", "Pune Logistics",       "INV-1006", date(2026, 7, 18), 31000, 5580, 0, 0),
    # Not in 2B at all -> MISSING_IN_2B
    ("24GGGGG7777G1Z7", "Vora Electricals",     "INV-1007", date(2026, 7, 22), 58000, 0, 5220, 5220),
    ("24HHHHH8888H1Z8", "Desai Printers",       "INV-1008", date(2026, 7, 25), 12000, 0, 1080, 1080),
]

B2_ROWS = [
    ("24AAAAA1111A1Z1", "Sharma Steel Traders", "INV-1001", date(2026, 7, 3), 150000, 0, 13500, 13500),
    ("24BBBBB2222B1Z2", "Patel Packaging",      "INV-1002", date(2026, 7, 5), 82000, 0, 7380, 7380),
    ("27CCCCC3333C1Z3", "Mumbai Freight Co",    "INV-1003", date(2026, 7, 8), 45000, 8100, 0, 0),
    ("24DDDDD4444D1Z4", "Gandhi Hardware",      "INV-1004", date(2026, 7, 11), 23500, 0, 2115, 2115),
    ("24EEEEE5555E1Z5", "Shah Chemicals",       "INV-1005", date(2026, 7, 14), 90000, 0, 8100, 8100),
    ("27FFFFF6666F1Z6", "Pune Logistics",       "INV-1006", date(2026, 7, 20), 31000, 5580, 0, 0),
    # Supplier filed an invoice the client never booked -> MISSING_IN_PR
    ("24IIIII9999I1Z9", "Joshi Stationers",     "INV-2201", date(2026, 7, 28), 7400, 0, 666, 666),
]

SALES_ROWS = [
    ("24JJJJJ1010J1Z0", "Modern Retail LLP", "S-501", date(2026, 7, 4), 320000, 0, 28800, 28800),
    ("27KKKKK1111K1Z1", "Nashik Distributors", "S-502", date(2026, 7, 12), 185000, 33300, 0, 0),
    ("24LLLLL1212L1Z2", "Rajkot Wholesale", "S-503", date(2026, 7, 21), 96500, 0, 8685, 8685),
]


def _write_workbook(path: Path, title: str, rows, itc_column: bool):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = title[:31]
    headers = [
        "GSTIN of supplier", "Trade/Legal name", "Invoice number", "Invoice Date",
        "Taxable Value", "Integrated Tax", "Central Tax", "State/UT Tax", "Invoice Value",
    ]
    if itc_column:
        headers.append("ITC Availability")
    sheet.append(headers)
    for gstin, name, inv, dt, taxable, igst, cgst, sgst in rows:
        row = [gstin, name, inv, dt, taxable, igst, cgst, sgst, taxable + igst + cgst + sgst]
        if itc_column:
            row.append("Yes")
        sheet.append(row)
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(path)


def write_samples():
    _write_workbook(SAMPLE_DIR / "purchase_register_july_2026.xlsx", "Purchase Register", PR_ROWS, False)
    _write_workbook(SAMPLE_DIR / "gstr2b_july_2026.xlsx", "GSTR-2B", B2_ROWS, True)
    _write_workbook(SAMPLE_DIR / "gstr1_sales_july_2026.xlsx", "GSTR-1 Sales", SALES_ROWS, False)
    print("sample workbooks written to", SAMPLE_DIR)


if __name__ == "__main__":
    if "--reset" in sys.argv:
        reset_db()
    seed()
    write_samples()
