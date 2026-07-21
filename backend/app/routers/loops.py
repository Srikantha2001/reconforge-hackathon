from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models
from ..actors import is_valid_actor
from ..db import get_db
from ..llm import get_provider
from ..routers.configs import config_to_out
from ..schemas import (
    ConfigOut,
    LoopAAggregateGroup,
    LoopAProposeOut,
    LoopAProposeRequest,
    LoopAWhatIfOut,
    LoopAWhatIfRequest,
    ResolutionMemoryOut,
)
from ..services import aggregate_manual_matches, propose_loop_a_config, what_if

router = APIRouter(prefix="/api", tags=["loops"])


@router.get("/runs/{run_id}/loop-a/aggregate", response_model=List[LoopAAggregateGroup])
def loop_a_aggregate(run_id: int, db: Session = Depends(get_db)):
    run = db.get(models.Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return aggregate_manual_matches(db, run_id)


@router.post("/runs/{run_id}/loop-a/propose", response_model=LoopAProposeOut)
def loop_a_propose(run_id: int, body: LoopAProposeRequest, db: Session = Depends(get_db)):
    if not is_valid_actor(body.actor_id):
        raise HTTPException(status_code=400, detail=f"Unknown actor_id '{body.actor_id}'")
    run = db.get(models.Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    groups = aggregate_manual_matches(db, run_id)
    group = next(
        (g for g in groups if g["field_a"] == body.field_a and g["field_b"] == body.field_b and g["type"] == body.type),
        None,
    )
    if not group:
        raise HTTPException(status_code=400, detail="No aggregated manual-match signal for that rule yet")

    provider = get_provider()
    new_config, rationale = propose_loop_a_config(
        db, current_config=run.config, group=group, provider=provider, actor_id=body.actor_id
    )
    db.commit()
    db.refresh(new_config)
    return LoopAProposeOut(new_config=config_to_out(new_config), rationale=rationale)


@router.post("/runs/{run_id}/loop-a/what-if", response_model=LoopAWhatIfOut)
def loop_a_what_if(run_id: int, body: LoopAWhatIfRequest, db: Session = Depends(get_db)):
    run = db.get(models.Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    candidate = db.get(models.ReconConfig, body.candidate_config_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate config not found")
    result = what_if(db, run=run, candidate_config=candidate)
    return LoopAWhatIfOut(**result)


@router.get("/resolution-memory", response_model=List[ResolutionMemoryOut])
def list_resolution_memory(db: Session = Depends(get_db)):
    return (
        db.query(models.ResolutionMemory)
        .order_by(models.ResolutionMemory.updated_at.desc())
        .all()
    )
