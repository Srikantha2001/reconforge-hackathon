from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models
from ..actors import is_valid_actor
from ..config import get_settings
from ..db import get_db
from ..llm import get_provider
from ..schemas import (
    AdviseOut,
    AdviseRequest,
    BreakOut,
    ChaserOut,
    ManualMatchRequest,
    ResolveBreakRequest,
)
from ..services import advise_break, audit, break_row_dict, record_manual_match, resolve_break

router = APIRouter(prefix="/api/breaks", tags=["breaks"])
settings = get_settings()


def _get_break(db: Session, break_id: int) -> models.Break:
    brk = db.get(models.Break, break_id)
    if not brk:
        raise HTTPException(status_code=404, detail="Break not found")
    return brk


def _require_actor(actor_id: str) -> None:
    if not is_valid_actor(actor_id):
        raise HTTPException(status_code=400, detail=f"Unknown actor_id '{actor_id}'")


@router.get("/{break_id}", response_model=BreakOut)
def get_break(break_id: int, db: Session = Depends(get_db)):
    return _get_break(db, break_id)


@router.post("/{break_id}/advise", response_model=AdviseOut)
def advise(break_id: int, body: AdviseRequest, db: Session = Depends(get_db)):
    _require_actor(body.actor_id)
    brk = _get_break(db, break_id)
    provider = get_provider()
    result = advise_break(db, brk=brk, actor_id=body.actor_id, provider=provider, threshold=settings.stp_threshold)
    db.commit()
    return AdviseOut(**result)


@router.post("/{break_id}/chaser", response_model=ChaserOut)
def chaser(break_id: int, body: AdviseRequest, db: Session = Depends(get_db)):
    _require_actor(body.actor_id)
    brk = _get_break(db, break_id)
    provider = get_provider()
    draft = provider.draft_chaser(break_row_dict(brk))

    audit(
        db,
        actor_id=body.actor_id,
        action="chaser_drafted",
        entity_type="break",
        entity_id=brk.id,
        after=draft,
    )
    db.commit()
    return ChaserOut(**draft)


@router.post("/{break_id}/manual-match", response_model=BreakOut)
def manual_match(break_id: int, body: ManualMatchRequest, db: Session = Depends(get_db)):
    _require_actor(body.actor_id)
    brk = _get_break(db, break_id)
    run = db.get(models.Run, brk.run_id)

    row_a = body.row_a or brk.row_a
    row_b = body.row_b or brk.row_b
    if row_a is None or row_b is None:
        raise HTTPException(
            status_code=400,
            detail="This is a one-sided break — provide the counterpart row_a/row_b explicitly",
        )

    record_manual_match(db, run=run, brk=brk, row_a=row_a, row_b=row_b, actor_id=body.actor_id)
    db.commit()
    db.refresh(brk)
    return brk


@router.post("/{break_id}/resolve", response_model=BreakOut)
def resolve(break_id: int, body: ResolveBreakRequest, db: Session = Depends(get_db)):
    _require_actor(body.actor_id)
    brk = _get_break(db, break_id)
    resolve_break(
        db,
        brk=brk,
        actor_id=body.actor_id,
        confirmed_archetype=body.confirmed_archetype,
        confirmed_resolution=body.confirmed_resolution,
    )
    db.commit()
    db.refresh(brk)
    return brk
