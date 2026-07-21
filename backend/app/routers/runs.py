import uuid
from collections import Counter
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from .. import models
from ..actors import is_valid_actor
from ..config import get_settings
from ..db import get_db
from ..schemas import BreakOut, DashboardOut, ReproducibilityCheckOut, RunOut
from ..services import execute_run, read_csv_path, reproducibility_check, save_bytes

router = APIRouter(prefix="/api/runs", tags=["runs"])

settings = get_settings()
SEED_DIR = Path(__file__).resolve().parent.parent.parent / "data"
UPLOAD_DIR = Path(settings.upload_dir)


@router.post("", response_model=RunOut)
async def create_run(
    config_id: int = Form(...),
    actor_id: str = Form(...),
    use_seed: bool = Form(False),
    ledger_file: Optional[UploadFile] = File(None),
    statement_file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
):
    if not is_valid_actor(actor_id):
        raise HTTPException(status_code=400, detail=f"Unknown actor_id '{actor_id}'")

    cfg = db.get(models.ReconConfig, config_id)
    if not cfg:
        raise HTTPException(status_code=404, detail="Config not found")
    if cfg.status != "approved":
        raise HTTPException(status_code=400, detail="Only an approved config can be run")

    if use_seed:
        file_a_path, file_b_path = str(SEED_DIR / "ledger.csv"), str(SEED_DIR / "statement.csv")
        if not Path(file_a_path).exists() or not Path(file_b_path).exists():
            raise HTTPException(status_code=400, detail="Seed data not found — generate it first")
    else:
        if ledger_file is None or statement_file is None:
            raise HTTPException(status_code=400, detail="Both ledger_file and statement_file are required unless use_seed=true")
        run_dir = UPLOAD_DIR / str(uuid.uuid4())
        file_a_path = save_bytes(await ledger_file.read(), run_dir, "ledger.csv")
        file_b_path = save_bytes(await statement_file.read(), run_dir, "statement.csv")

    df_a = read_csv_path(file_a_path)
    df_b = read_csv_path(file_b_path)

    run = execute_run(
        db,
        config=cfg,
        df_a=df_a,
        df_b=df_b,
        file_a_ref=file_a_path,
        file_b_ref=file_b_path,
        actor_id=actor_id,
    )
    db.commit()
    db.refresh(run)
    return run


@router.get("/{run_id}", response_model=RunOut)
def get_run(run_id: int, db: Session = Depends(get_db)):
    run = db.get(models.Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.get("", response_model=List[RunOut])
def list_runs(config_id: Optional[int] = None, db: Session = Depends(get_db)):
    q = db.query(models.Run)
    if config_id:
        q = q.filter(models.Run.config_id == config_id)
    return q.order_by(models.Run.created_at.desc()).all()


@router.post("/{run_id}/reproducibility-check", response_model=ReproducibilityCheckOut)
def check_reproducibility(run_id: int, db: Session = Depends(get_db)):
    run = db.get(models.Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    recomputed_hash, reproducible = reproducibility_check(db, run)
    return ReproducibilityCheckOut(
        run_id=run.id,
        original_hash=run.output_hash,
        recomputed_hash=recomputed_hash,
        reproducible=reproducible,
    )


@router.get("/{run_id}/breaks", response_model=List[BreakOut])
def list_breaks(run_id: int, db: Session = Depends(get_db)):
    run = db.get(models.Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return (
        db.query(models.Break)
        .filter(models.Break.run_id == run_id)
        .order_by(models.Break.severity.desc(), models.Break.break_key)
        .all()
    )


@router.get("/{run_id}/dashboard", response_model=DashboardOut)
def dashboard(run_id: int, db: Session = Depends(get_db)):
    run = db.get(models.Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    breaks = db.query(models.Break).filter(models.Break.run_id == run_id).all()
    return DashboardOut(
        run=run,
        archetype_counts=dict(Counter(b.archetype for b in breaks)),
        severity_counts=dict(Counter(b.severity for b in breaks)),
        status_counts=dict(Counter(b.status for b in breaks)),
    )
