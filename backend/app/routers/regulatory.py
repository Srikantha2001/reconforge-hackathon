"""Regulatory endpoints (P6): EMIR notifications, CASS daily + pack, CSDR stub.

EMIR list/approve is open to CHECKER or DSI; CASS views to CHECKER. CSDR is
deliberately minimal — an empty typed list so the UI tab renders a clean
"no penalties" state.
"""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import services_regulatory as reg
from ..auth import require_role
from ..db import get_db
from ..schemas import CassReconciliationOut, RegulatoryNotificationOut

router = APIRouter(prefix="/api/regulatory", tags=["regulatory"])


@router.get("/emir", response_model=List[RegulatoryNotificationOut])
def emir_notifications(
    status: str = "DRAFT",
    user: dict = Depends(require_role("CHECKER", "DSI")),
    db: Session = Depends(get_db),
):
    return reg.list_emir_notifications(db, status=status)


@router.post("/emir/{notification_id}/approve", response_model=RegulatoryNotificationOut)
def approve_emir(
    notification_id: int,
    user: dict = Depends(require_role("CHECKER", "DSI")),
    db: Session = Depends(get_db),
):
    return reg.approve_emir_notification(db, notification_id, approver_id=user["user_id"])


@router.get("/cass/daily/{date}", response_model=CassReconciliationOut)
def cass_daily(
    date: str,
    user: dict = Depends(require_role("CHECKER", "DSI")),
    db: Session = Depends(get_db),
):
    return reg.cass_daily(db, date)


@router.get("/cass/resolution-pack/{date}")
def cass_resolution_pack(
    date: str,
    user: dict = Depends(require_role("CHECKER", "DSI")),
    db: Session = Depends(get_db),
):
    return reg.cass_resolution_pack(db, date)


@router.get("/csdr")
def csdr_penalties(user: dict = Depends(require_role("CHECKER", "DSI"))):
    # Deliberately minimal (spec): no CSDR penalty engine — empty result set.
    return []
