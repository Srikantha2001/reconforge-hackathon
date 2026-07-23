"""Loop endpoints v2 (P8): Loop A detect/propose/what-if, Loop B memory.

Loop A reads the force-matched breaks (governance FORCE_MATCH writes ManualMatch
signals), detects a systemic pattern, and proposes a re-versioned config
(PENDING_APPROVAL) — approved via the config approve endpoint (maker ≠ checker).
"""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models
from ..auth import get_current_user, require_role
from ..db import get_db
from ..routers.configs import config_to_out
from ..schemas import LoopAProposeOutV2, LoopAWhatIfOut, LoopAWhatIfRequest, ResolutionMemoryOut
from ..services_run import loop_a_detect, loop_a_manual_matches, loop_a_propose, loop_a_what_if

router = APIRouter(prefix="/api", tags=["loops"])


def _require_run(db: Session, run_id: int) -> models.Run:
    run = db.get(models.Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.get("/runs/{run_id}/loop-a/aggregate")
def loop_a_aggregate(run_id: int, user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_run(db, run_id)
    pattern = loop_a_detect(db, run_id)
    return {"pattern": pattern, "manual_match_count": len(loop_a_manual_matches(db, run_id))}


@router.post("/runs/{run_id}/loop-a/propose", response_model=LoopAProposeOutV2)
def loop_a_propose_route(
    run_id: int,
    user: dict = Depends(require_role("MAKER")),
    db: Session = Depends(get_db),
):
    run = _require_run(db, run_id)
    result = loop_a_propose(db, run, actor_id=user["user_id"])
    if not result:
        raise HTTPException(status_code=400, detail="No systemic pattern detected yet (need 4+ force-matched breaks)")
    return LoopAProposeOutV2(
        new_config=config_to_out(result["new_config"]),
        rationale=result["rationale"],
        cap_note=result["cap_note"],
    )


@router.post("/runs/{run_id}/loop-a/what-if", response_model=LoopAWhatIfOut)
def loop_a_what_if_route(
    run_id: int,
    body: LoopAWhatIfRequest,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    run = _require_run(db, run_id)
    candidate = db.get(models.ReconConfig, body.candidate_config_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate config not found")
    return LoopAWhatIfOut(**loop_a_what_if(db, run, candidate))


@router.get("/resolution-memory", response_model=List[ResolutionMemoryOut])
def list_resolution_memory(user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(models.ResolutionMemory).order_by(models.ResolutionMemory.updated_at.desc()).all()
