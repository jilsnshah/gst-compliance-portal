from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.serializers import user_out
from app.core.db import get_db
from app.core.enums import AuditAction
from app.core.security import create_access_token, verify_password
from app.models import User
from app.schemas.requests import LoginRequest
from app.services import audit

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    """Dev-stage password login. Stage 2 replaces this with Google/Firebase
    sign-in; the token contract stays identical."""
    user = db.execute(select(User).where(User.email == payload.email.lower())).scalars().first()
    if not user or not user.hashed_password or not verify_password(
        payload.password, user.hashed_password
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account disabled")

    user.last_login_at = datetime.utcnow()
    audit.record(db, user, AuditAction.LOGIN, "User", f"{user.email} logged in", target_id=user.id)
    db.commit()

    token = create_access_token(str(user.id), {"role": user.role, "email": user.email})
    return {"access_token": token, "token_type": "bearer", "user": user_out(user)}


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return user_out(user)
