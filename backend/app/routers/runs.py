"""Run endpoints v2 (P8): execute, reproduce, position-proof, waterfall, summary.

Execution is MAKER-gated (actor from the JWT). A run persists the Run, its
Breaks + MatchLedger, and screens for EMIR; the analyze step (breaks router)
then classifies + routes. Position proof and waterfall come from re-deriving the
engine result over the run's stored inputs.
"""
from __future__ import annotations

import uuid
from collections import Counter
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from .. import models
from ..auth import get_current_user, require_role
from ..config import get_settings
from ..db import get_db
from ..engine.runner import reconcile
from ..schemas import (
    BreakOut,
    DashboardOut,
    PassStatOut,
    PositionProofOut,
    ReproducibilityCheckOut,
    RunOut,
    RunSummaryOut,
)
from ..services import save_bytes
from ..services_run import SEED_DIR, execute_run, read_csv_bytes, read_csv_path, reproduce

router = APIRouter(prefix="/api/runs", tags=["runs"])
settings = get_settings()
UPLOAD_DIR = Path(settings.upload_dir)


def _require_run(db: Session, run_id: int) -> models.Run:
    run = db.get(models.Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.post("", response_model=RunOut)
async def create_run(
    config_id: int = Form(...),
    use_seed: bool = Form(False),
    ledger_file: Optional[UploadFile] = File(None),
    statement_file: Optional[UploadFile] = File(None),
    user: dict = Depends(require_role("MAKER")),
    db: Session = Depends(get_db),
):
    cfg = db.get(models.ReconConfig, config_id)
    if not cfg:
        raise HTTPException(status_code=404, detail="Config not found")
    if cfg.status != "APPROVED":
        raise HTTPException(status_code=400, detail="Only an APPROVED config can be run")

    if use_seed:
        file_a_path = str(SEED_DIR / "internal_ibor.csv")
        file_b_path = str(SEED_DIR / "bny_mt535_custody.csv")
        if not Path(file_a_path).exists() or not Path(file_b_path).exists():
            raise HTTPException(status_code=400, detail="Seed data not found — generate it first")
    else:
        if ledger_file is None or statement_file is None:
            raise HTTPException(status_code=400, detail="Both files are required unless use_seed=true")
        run_dir = UPLOAD_DIR / str(uuid.uuid4())
        file_a_path = save_bytes(await ledger_file.read(), run_dir, "source_a.csv")
        file_b_path = save_bytes(await statement_file.read(), run_dir, "source_b.csv")

    df_a = read_csv_path(file_a_path)
    df_b = read_csv_path(file_b_path)
    run = execute_run(db, config=cfg, df_a=df_a, df_b=df_b, file_a_ref=file_a_path,
                      file_b_ref=file_b_path, actor_id=user["user_id"])
    db.commit()
    db.refresh(run)
    return run


@router.get("/{run_id}", response_model=RunOut)
def get_run(run_id: int, user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    return _require_run(db, run_id)


@router.get("", response_model=List[RunOut])
def list_runs(config_id: Optional[int] = None, user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(models.Run).filter(models.Run.is_client_run == False)  # noqa: E712
    if config_id:
        q = q.filter(models.Run.config_id == config_id)
    return q.order_by(models.Run.created_at.desc()).all()


def _repro_response(db: Session, run: models.Run) -> ReproducibilityCheckOut:
    recomputed, ok = reproduce(db, run)
    return ReproducibilityCheckOut(run_id=run.id, original_hash=run.output_hash,
                                   recomputed_hash=recomputed, reproducible=ok)


@router.post("/{run_id}/reproduce", response_model=ReproducibilityCheckOut)
def reproduce_run(run_id: int, user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    return _repro_response(db, _require_run(db, run_id))


@router.post("/{run_id}/reproducibility-check", response_model=ReproducibilityCheckOut)
def reproducibility_check_alias(run_id: int, user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    return _repro_response(db, _require_run(db, run_id))


@router.get("/{run_id}/position-proof", response_model=List[PositionProofOut])
def position_proof(run_id: int, user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    run = _require_run(db, run_id)
    result = reconcile(read_csv_path(run.file_a_ref), read_csv_path(run.file_b_ref),
                       run.config.config_json, data_dir=SEED_DIR)
    return [PositionProofOut(**result.position_proof["A"]), PositionProofOut(**result.position_proof["B"])]


@router.get("/{run_id}/waterfall", response_model=List[PassStatOut])
def waterfall(run_id: int, user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    run = _require_run(db, run_id)
    result = reconcile(read_csv_path(run.file_a_ref), read_csv_path(run.file_b_ref),
                       run.config.config_json, data_dir=SEED_DIR)
    return [PassStatOut(**p) for p in result.pass_stats]


@router.get("/{run_id}/summary", response_model=RunSummaryOut)
def summary(run_id: int, user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    run = _require_run(db, run_id)
    breaks = db.query(models.Break).filter(models.Break.run_id == run_id).all()
    return RunSummaryOut(
        run=RunOut.model_validate(run),
        position_proof_status=run.position_proof_status,
        archetype_counts=dict(Counter(b.archetype for b in breaks if b.archetype)),
        status_counts=dict(Counter(b.status for b in breaks)),
        regulatory_escalation_count=run.regulatory_escalation_count,
    )


@router.get("/{run_id}/breaks", response_model=List[BreakOut])
def list_breaks(run_id: int, user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_run(db, run_id)
    return (
        db.query(models.Break)
        .filter(models.Break.run_id == run_id)
        .order_by(models.Break.severity.desc(), models.Break.break_key)
        .all()
    )


@router.get("/{run_id}/dashboard", response_model=DashboardOut)
def dashboard(run_id: int, user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    run = _require_run(db, run_id)
    breaks = db.query(models.Break).filter(models.Break.run_id == run_id).all()
    return DashboardOut(
        run=run,
        archetype_counts=dict(Counter(b.archetype for b in breaks if b.archetype)),
        severity_counts=dict(Counter(b.severity for b in breaks)),
        status_counts=dict(Counter(b.status for b in breaks)),
    )
