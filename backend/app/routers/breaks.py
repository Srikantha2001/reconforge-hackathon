"""Break endpoints v2 (P8): analyze (SME+Judge), get, filter, regulatory list.

Analyze is MAKER-gated and runs the P7 agents over a run's open breaks,
persisting archetype/causal/route and auto-resolving the STP band. The
regulatory list is CHECKER/DSI-gated.
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models
from ..auth import get_current_user, require_role
from ..db import get_db
from ..schemas import AnalyzeRequest, BreakAnalysisOut, BreakOut
from ..services_run import analyze_run_breaks

router = APIRouter(prefix="/api/breaks", tags=["breaks"])


def _get_break(db: Session, break_id: int) -> models.Break:
    brk = db.get(models.Break, break_id)
    if not brk:
        raise HTTPException(status_code=404, detail="Break not found")
    return brk


@router.post("/analyze", response_model=List[BreakAnalysisOut])
def analyze(
    body: AnalyzeRequest,
    user: dict = Depends(require_role("MAKER")),
    db: Session = Depends(get_db),
):
    run = db.get(models.Run, body.run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    analyses = analyze_run_breaks(db, run, actor_id=user["user_id"])
    return [
        BreakAnalysisOut(
            break_id=a["break_id"],
            archetype=a["sme"]["archetype"],
            causal_origin=a["sme"]["causal_origin"],
            field_most_responsible=a["sme"]["field_most_responsible"],
            confidence=a["sme"]["confidence"],
            autonomy_route=a["judge"]["autonomy_route"],
            refuse_to_classify=a["sme"]["refuse_to_classify"],
            routing_rationale=a["judge"]["routing_rationale"],
        )
        for a in analyses
    ]


@router.get("/regulatory", response_model=List[BreakOut])
def regulatory_breaks(
    user: dict = Depends(require_role("CHECKER", "DSI")),
    db: Session = Depends(get_db),
):
    return (
        db.query(models.Break)
        .filter(models.Break.regulatory_escalation_required == True)  # noqa: E712
        .order_by(models.Break.created_at.desc())
        .all()
    )


@router.get("/run/{run_id}", response_model=List[BreakOut])
def breaks_by_run(
    run_id: int,
    status: Optional[str] = None,
    archetype: Optional[str] = None,
    regulatory_only: bool = False,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(models.Break).filter(models.Break.run_id == run_id)
    if status:
        q = q.filter(models.Break.status == status)
    if archetype:
        q = q.filter(models.Break.archetype == archetype)
    if regulatory_only:
        q = q.filter(models.Break.regulatory_escalation_required == True)  # noqa: E712
    return q.order_by(models.Break.severity.desc(), models.Break.break_key).all()


@router.get("/{break_id}", response_model=BreakOut)
def get_break(break_id: int, user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    return _get_break(db, break_id)
