"""Governance endpoints (P5): maker submit, checker approve, pending, audit.

Identity comes from the JWT (P4): the maker/checker is the token's subject, and
the routes are role-gated (MAKER submits, CHECKER approves). This is the first
place the v2 auth is wired into a real workflow; the legacy config/run/break
endpoints are rebuilt against the token in P8.
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models, services_governance as gov
from ..auth import get_current_user, require_role
from ..db import get_db
from ..schemas import (
    AuditLogOut,
    CheckerApproveRequest,
    CheckerDecisionOut,
    GovernanceActionOut,
    JournalEntryOut,
    MakerSubmitOut,
    MakerSubmitRequest,
    PendingActionOut,
)

router = APIRouter(prefix="/api/governance", tags=["governance"])


@router.post("/maker-submit", response_model=MakerSubmitOut)
def maker_submit(
    body: MakerSubmitRequest,
    user: dict = Depends(require_role("MAKER")),
    db: Session = Depends(get_db),
):
    result = gov.maker_submit(
        db,
        break_id=body.break_id,
        maker_id=user["user_id"],
        action_type=body.action_type,
        notes=body.notes,
    )
    return MakerSubmitOut(
        action=GovernanceActionOut.model_validate(result["action"]),
        journal_entry=JournalEntryOut.model_validate(result["journal_entry"])
        if result["journal_entry"] else None,
    )


@router.post("/checker-approve", response_model=CheckerDecisionOut)
def checker_approve(
    body: CheckerApproveRequest,
    user: dict = Depends(require_role("CHECKER")),
    db: Session = Depends(get_db),
):
    result = gov.checker_approve(
        db,
        action_id=body.action_id,
        checker_id=user["user_id"],
        approved=body.approved,
        notes=body.notes,
    )
    return CheckerDecisionOut(
        status=result["status"],
        journal_entry=JournalEntryOut.model_validate(result["journal_entry"])
        if result["journal_entry"] else None,
    )


@router.get("/pending", response_model=List[PendingActionOut])
def pending(
    user: dict = Depends(require_role("CHECKER")),
    db: Session = Depends(get_db),
):
    rows = gov.list_pending(db)
    return [
        PendingActionOut(
            **GovernanceActionOut.model_validate(action).model_dump(),
            time_remaining_seconds=remaining,
        )
        for action, remaining in rows
    ]


@router.get("/audit", response_model=List[AuditLogOut])
def audit_log(
    page: int = 1,
    page_size: int = 50,
    actor_id: Optional[str] = None,
    entity_type: Optional[str] = None,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(models.AuditLog)
    if actor_id:
        q = q.filter(models.AuditLog.actor_id == actor_id)
    if entity_type:
        q = q.filter(models.AuditLog.entity_type == entity_type)
    offset = max(0, (page - 1) * page_size)
    return (
        q.order_by(models.AuditLog.timestamp.desc())
        .offset(offset)
        .limit(page_size)
        .all()
    )
