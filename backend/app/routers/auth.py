"""Auth endpoints (P4): login + current-user.

``POST /api/auth/login`` exchanges email+password for a JWT; ``GET /api/auth/me``
echoes the token's identity. ``GET /api/auth/probe-maker`` is a tiny
role-gated route that exists only to demonstrate (and test) that
``require_role`` returns 403 for the wrong role — the real per-endpoint role
gates land in P8 when the config/run/break endpoints are rebuilt for v2.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..auth import authenticate, create_access_token, get_current_user, require_role
from ..db import get_db
from ..schemas import LoginRequest, TokenResponse, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = authenticate(db, body.email, body.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    token = create_access_token(user_id=str(user.id), role=user.role, email=user.email)
    return TokenResponse(
        access_token=token,
        user_id=str(user.id),
        role=user.role,
        email=user.email,
        name=user.name,
    )


@router.get("/me", response_model=UserOut)
def me(user: dict = Depends(get_current_user)):
    return UserOut(user_id=user["user_id"], email=user["email"], role=user["role"])


@router.get("/probe-maker")
def probe_maker(user: dict = Depends(require_role("MAKER"))):
    """Role-gating demonstration/test hook (MAKER only)."""
    return {"ok": True, "role": user["role"]}
