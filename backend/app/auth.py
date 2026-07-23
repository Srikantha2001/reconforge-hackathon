"""JWT authentication and role-based access control (P4).

Replaces the pre-auth "acting as" selector: identity now comes from a signed
JWT, and every actor recorded in the audit trail is the token's subject. Five
seeded demo users cover the five roles (ADMIN, MAKER, CHECKER, CLIENT, DSI).

Password hashing uses ``bcrypt`` directly (portable wheels, no passlib version
coupling); tokens use ``PyJWT`` (HS256) with the secret + expiry from settings.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import bcrypt
import jwt
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import User

settings = get_settings()

ROLES = ("ADMIN", "MAKER", "CHECKER", "CLIENT", "DSI")

# The five demo users seeded at startup (email, password, name, role, org).
DEMO_USERS: List[Dict[str, Any]] = [
    {"email": "maker@db.com", "password": "maker123", "name": "Mia Maker", "role": "MAKER", "client_org": None},
    {"email": "checker@db.com", "password": "checker123", "name": "Cai Checker", "role": "CHECKER", "client_org": None},
    {"email": "admin@db.com", "password": "admin123", "name": "Avery Admin", "role": "ADMIN", "client_org": None},
    {"email": "client@alphacapital.com", "password": "client123", "name": "Alpha Capital", "role": "CLIENT", "client_org": "Alpha Capital"},
    {"email": "dsi@db.com", "password": "dsi123", "name": "Dana DSI", "role": "DSI", "client_org": None},
]


# --- Password hashing ------------------------------------------------------
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# --- Tokens ----------------------------------------------------------------
def create_access_token(user_id: str, role: str, email: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=settings.access_token_expire_hours)
    payload = {"sub": str(user_id), "role": role, "email": email, "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def verify_token(token: str) -> Dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    if not payload.get("sub") or not payload.get("role"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Malformed token")
    return {"user_id": payload["sub"], "role": payload["role"], "email": payload.get("email")}


# --- Dependencies ----------------------------------------------------------
def get_current_user(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    """FastAPI dependency: extract + validate the Bearer token."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization.split(" ", 1)[1].strip()
    return verify_token(token)


def require_role(*roles: str):
    """Dependency factory: 403 unless the current user's role is allowed."""

    def checker(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        if user["role"] not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires role in {roles}; you are {user['role']}",
            )
        return user

    return checker


# --- User lookup + seeding -------------------------------------------------
def authenticate(db: Session, email: str, password: str) -> Optional[User]:
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user and user.is_active and verify_password(password, user.hashed_password):
        return user
    return None


def seed_demo_users(db: Session) -> int:
    """Create any missing demo users. Idempotent; returns how many were added."""
    created = 0
    for u in DEMO_USERS:
        exists = db.execute(select(User).where(User.email == u["email"])).scalar_one_or_none()
        if exists:
            continue
        db.add(
            User(
                email=u["email"],
                name=u["name"],
                role=u["role"],
                client_org=u["client_org"],
                is_active=True,
                hashed_password=hash_password(u["password"]),
            )
        )
        created += 1
    if created:
        db.commit()
    return created
