from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.serializers import client_out, employee_out, entity_out, user_out
from app.core.db import get_db
from app.core.enums import AuditAction, Role
from app.core.security import hash_password
from app.models import (
    Client,
    ClientAssignment,
    ClientUser,
    Employee,
    Entity,
    User,
)
from app.schemas.requests import AssignmentCreate, ClientCreate, EntityCreate, UserCreate
from app.services import audit
from app.services.permissions import (
    assert_client_access,
    require_admin,
    require_ca,
    visible_client_ids,
)

router = APIRouter(prefix="/api", tags=["masters"])


# ---------------------------------------------------------------- clients
@router.get("/clients")
def list_clients(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    stmt = select(Client).order_by(Client.name)
    ids = visible_client_ids(db, user)
    if ids is not None:
        stmt = stmt.where(Client.id.in_(ids or [-1]))
    return [client_out(c) for c in db.execute(stmt).scalars().all()]


@router.post("/clients", status_code=201)
def create_client(
    payload: ClientCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    """Creates the client and the one login they sign in with, together --
    a client without a login could never reach their own portal."""
    require_admin(user)
    email = payload.email.lower()
    if db.execute(select(User).where(User.email == email)).scalars().first():
        raise HTTPException(status.HTTP_409_CONFLICT, "That email already has a login")

    client = Client(name=payload.name, phone=payload.phone)
    db.add(client)
    db.flush()

    login = User(
        email=email,
        full_name=payload.name,
        phone=payload.phone,
        hashed_password=hash_password(payload.password),
        role=Role.CLIENT,
    )
    db.add(login)
    db.flush()
    db.add(ClientUser(user_id=login.id, client_id=client.id, is_primary_contact=True))
    db.flush()

    audit.record(
        db, user, AuditAction.CREATE, "Client",
        f"Client {client.name} created with login {email}",
        target_id=client.id, client_id=client.id,
    )
    db.commit()
    db.refresh(client)
    return client_out(client)


@router.get("/clients/{client_id}")
def get_client(
    client_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    assert_client_access(db, user, client_id)
    client = db.get(Client, client_id)
    if not client:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")
    out = client_out(client)
    out["entities"] = [entity_out(e) for e in client.entities]
    return out


# --------------------------------------------------------------- entities
@router.get("/entities")
def list_entities(
    client_id: int = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    stmt = select(Entity).order_by(Entity.legal_name)
    ids = visible_client_ids(db, user)
    if ids is not None:
        stmt = stmt.where(Entity.client_id.in_(ids or [-1]))
    if client_id:
        assert_client_access(db, user, client_id)
        stmt = stmt.where(Entity.client_id == client_id)
    return [entity_out(e) for e in db.execute(stmt).scalars().all()]


@router.post("/entities", status_code=201)
def create_entity(
    payload: EntityCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    require_ca(user)
    assert_client_access(db, user, payload.client_id)
    if db.execute(
        select(Entity).where(Entity.file_number == payload.file_number)
    ).scalars().first():
        raise HTTPException(status.HTTP_409_CONFLICT, "File number already exists")
    data = payload.model_dump()
    data["gstin"] = data["gstin"].upper()
    if db.execute(select(Entity).where(Entity.gstin == data["gstin"])).scalars().first():
        raise HTTPException(status.HTTP_409_CONFLICT, "That GSTIN already has a file")
    entity = Entity(**data)
    db.add(entity)
    db.flush()
    audit.record(
        db, user, AuditAction.CREATE, "Entity",
        f"File {entity.file_number} ({entity.legal_name}, {entity.gstin}) created",
        target_id=entity.id, client_id=entity.client_id,
    )
    db.commit()
    return entity_out(entity)


# ------------------------------------------------------ employees & users
@router.get("/employees")
def list_employees(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_ca(user)
    return [employee_out(e) for e in db.execute(select(Employee)).scalars().all()]


@router.get("/users")
def list_users(
    client_id: Optional[int] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Client logins, so an admin can see who is actually able to sign in."""
    require_ca(user)
    stmt = (
        select(User)
        .join(ClientUser, ClientUser.user_id == User.id)
        .order_by(User.full_name)
    )
    ids = visible_client_ids(db, user)
    if ids is not None:
        stmt = stmt.where(ClientUser.client_id.in_(ids or [-1]))
    if client_id:
        assert_client_access(db, user, client_id)
        stmt = stmt.where(ClientUser.client_id == client_id)
    return [user_out(u) for u in db.execute(stmt).unique().scalars().all()]


@router.post("/users", status_code=201)
def create_user(
    payload: UserCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    require_admin(user)
    if db.execute(select(User).where(User.email == payload.email.lower())).scalars().first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

    new_user = User(
        email=payload.email.lower(),
        full_name=payload.full_name,
        phone=payload.phone,
        hashed_password=hash_password(payload.password),
        role=payload.role,
    )
    db.add(new_user)
    db.flush()

    if payload.role in (Role.CA_EMPLOYEE, Role.CA_ADMIN):
        db.add(
            Employee(
                user_id=new_user.id,
                employee_code=payload.employee_code or f"EMP{new_user.id:03d}",
                designation=payload.designation,
            )
        )
    elif payload.role == Role.CLIENT:
        if not payload.client_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "client_id required for CLIENT role")
        db.add(ClientUser(user_id=new_user.id, client_id=payload.client_id))

    db.flush()
    audit.record(
        db, user, AuditAction.CREATE, "User", f"User {new_user.email} created as {payload.role}",
        target_id=new_user.id, client_id=payload.client_id,
    )
    db.commit()
    db.refresh(new_user)
    return user_out(new_user)


@router.post("/assignments", status_code=201)
def assign_client(
    payload: AssignmentCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    require_admin(user)
    existing = db.execute(
        select(ClientAssignment).where(
            ClientAssignment.client_id == payload.client_id,
            ClientAssignment.employee_id == payload.employee_id,
        )
    ).scalars().first()
    if existing:
        return {"id": existing.id, "status": "already assigned"}
    assignment = ClientAssignment(**payload.model_dump())
    db.add(assignment)
    db.flush()
    audit.record(
        db, user, AuditAction.ASSIGNED, "ClientAssignment",
        f"Employee {payload.employee_id} assigned to client {payload.client_id}",
        target_id=assignment.id, client_id=payload.client_id,
    )
    db.commit()
    return {"id": assignment.id, "status": "assigned"}


@router.get("/assignments")
def list_assignments(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_ca(user)
    rows = db.execute(select(ClientAssignment)).scalars().all()
    return [
        {"id": a.id, "client_id": a.client_id, "employee_id": a.employee_id, "note": a.note}
        for a in rows
    ]
