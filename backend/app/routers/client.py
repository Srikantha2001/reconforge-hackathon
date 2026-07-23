"""Client portal (P8, CLIENT role): upload → run vs bank records → evidence.

A client uploads their own position file; it is reconciled against the bank's
IBOR records for their fund using the default APPROVED config. Clients only ever
see their OWN runs (isolation via Run.client_id), and results are simplified —
plain-English issue labels, no internal reasoning.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from .. import models
from ..auth import require_role
from ..config import get_settings
from ..db import get_db
from ..engine.archetype import ARCHETYPE_LABELS
from ..schemas import ClientBreakOut, ClientReconOut, ClientUploadOut, EvidencePack
from ..services import save_bytes
from ..services_run import SEED_DIR, execute_run, read_csv_bytes, read_csv_path

router = APIRouter(prefix="/api/client", tags=["client"])
settings = get_settings()
UPLOAD_DIR = Path(settings.upload_dir)


def _default_config(db: Session) -> models.ReconConfig:
    cfg = (
        db.query(models.ReconConfig)
        .filter(models.ReconConfig.status == "APPROVED")
        .order_by(models.ReconConfig.approved_at.desc())
        .first()
    )
    if not cfg:
        raise HTTPException(status_code=400, detail="No approved reconciliation config available yet")
    return cfg


def _owned_run(db: Session, run_id: int, user: dict) -> models.Run:
    run = db.get(models.Run, run_id)
    if not run or run.client_id != user["user_id"]:
        raise HTTPException(status_code=404, detail="Run not found")  # isolation: don't leak existence
    return run


@router.post("/upload", response_model=ClientUploadOut)
async def upload(
    fund_id: str = Form(...),
    recon_type: str = Form("POSITION"),
    file: UploadFile = File(...),
    user: dict = Depends(require_role("CLIENT")),
    db: Session = Depends(get_db),
):
    cfg = _default_config(db)

    # Side A = the bank's IBOR records for this fund; Side B = the client upload.
    ibor = read_csv_path(str(SEED_DIR / "internal_ibor.csv"))
    df_a = ibor[ibor["fund_id"].astype(str) == fund_id] if "fund_id" in ibor.columns else ibor
    if df_a.empty:
        raise HTTPException(status_code=400, detail=f"No bank records for fund '{fund_id}'")
    df_b = read_csv_bytes(await file.read())

    run_dir = UPLOAD_DIR / str(uuid.uuid4())
    save_bytes(df_a.to_csv(index=False).encode(), run_dir, "bank_a.csv")
    file_b_path = save_bytes(df_b.to_csv(index=False).encode(), run_dir, "client_b.csv")
    file_a_path = str(run_dir / "bank_a.csv")

    run = execute_run(
        db, config=cfg, df_a=df_a, df_b=df_b, file_a_ref=file_a_path, file_b_ref=file_b_path,
        actor_id=user["user_id"], client_id=user["user_id"], is_client_run=True,
    )
    db.commit()
    db.refresh(run)
    return ClientUploadOut(
        run_id=run.id, match_rate=float(run.match_rate), matched_count=run.matched_count,
        break_count=run.break_count, output_hash=run.output_hash,
    )


@router.get("/recon/{run_id}", response_model=ClientReconOut)
def recon(run_id: int, user: dict = Depends(require_role("CLIENT")), db: Session = Depends(get_db)):
    run = _owned_run(db, run_id, user)
    breaks = db.query(models.Break).filter(models.Break.run_id == run.id).all()
    return ClientReconOut(
        run_id=run.id,
        match_rate=float(run.match_rate),
        matched_count=run.matched_count,
        break_count=run.break_count,
        breaks=[_client_break(b) for b in breaks],
    )


@router.get("/break/{break_id}", response_model=ClientBreakOut)
def client_break(break_id: int, user: dict = Depends(require_role("CLIENT")), db: Session = Depends(get_db)):
    brk = db.get(models.Break, break_id)
    if not brk:
        raise HTTPException(status_code=404, detail="Break not found")
    _owned_run(db, brk.run_id, user)  # enforce ownership of the parent run
    return _client_break(brk)


def _client_break(brk: models.Break) -> ClientBreakOut:
    return ClientBreakOut(
        break_id=brk.id,
        isin=brk.isin,
        issue=ARCHETYPE_LABELS.get(brk.archetype, "Under review"),
        status="Open" if brk.status == "open" else "Resolved" if "RESOLVED" in brk.status else brk.status,
        amount=float(brk.amount_a) if brk.amount_a is not None else None,
    )


@router.get("/evidence/{run_id}", response_model=EvidencePack)
def evidence(run_id: int, user: dict = Depends(require_role("CLIENT")), db: Session = Depends(get_db)):
    run = _owned_run(db, run_id, user)
    # Hash the reconciliation FACTS only (not the generation timestamp) so the
    # document_hash is a stable, tamper-evident stamp of the same run.
    facts = {
        "run_id": run.id,
        "recon_name": run.config.recon_name,
        "match_rate": float(run.match_rate),
        "output_hash": run.output_hash,
        "position_proof_status": run.position_proof_status,
        "break_count": run.break_count,
    }
    blob = json.dumps(facts, sort_keys=True, separators=(",", ":"))
    document_hash = hashlib.sha256(blob.encode("utf-8")).hexdigest()
    return EvidencePack(
        **facts,
        generated_at=datetime.now(timezone.utc).isoformat(),
        document_hash=document_hash,
    )
