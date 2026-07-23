"""Config endpoints v2 (P8): author → submit → approve/reject, versions.

Identity + role come from the JWT (P4): MAKER authors/submits, CHECKER
approves/rejects (maker ≠ checker). Configs move DRAFT → PENDING_APPROVAL →
APPROVED, with the prior APPROVED version marked SUPERSEDED on a re-version.
Offline (stub provider) authoring degrades to the pre-approved securities recon
(the seed DEFAULT_CONFIG) — a real LLM would author a novel v2 config from the
description; either way the result is schema-validated before it is stored.
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models
from ..auth import get_current_user, require_role
from ..config_schema import ConfigValidationError, validate_and_repair
from ..db import get_db
from ..llm import get_provider
from ..schemas import AuthorConfigV2Request, ConfigDecisionRequest, ConfigOut
from ..seed.generator import DEFAULT_CONFIG
from ..services import audit

router = APIRouter(prefix="/api/configs", tags=["configs"])


def config_to_out(cfg: models.ReconConfig, repairs: Optional[List[str]] = None) -> ConfigOut:
    out = ConfigOut.model_validate(cfg)
    out.repairs_applied = repairs or []
    return out


def _author_v2_config(nl_description: str) -> tuple:
    """Return (valid_config_dict, repairs). Stub degrades to the seed recon."""
    provider = get_provider()
    raw = provider.author_config(nl_description, [], []) if nl_description else None
    if raw is not None:
        try:
            valid, repairs = validate_and_repair(raw)
            return valid, repairs
        except ConfigValidationError:
            pass
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    cfg["status"] = "DRAFT"
    return cfg, ["offline stub authoring degraded to the pre-approved recon"]


def _next_version(db: Session, recon_name: str) -> str:
    from ..agents import _bump_minor
    existing = (
        db.query(models.ReconConfig)
        .filter(models.ReconConfig.recon_name == recon_name)
        .order_by(models.ReconConfig.id.desc())
        .first()
    )
    return _bump_minor(existing.version) if existing else "1.0.0"


@router.post("/author", response_model=ConfigOut)
def author_config(
    body: AuthorConfigV2Request,
    user: dict = Depends(require_role("MAKER")),
    db: Session = Depends(get_db),
):
    valid_config, repairs = _author_v2_config(body.nl_description)
    if body.recon_name_hint:
        valid_config["recon_name"] = body.recon_name_hint
    valid_config["status"] = "DRAFT"

    recon_name = valid_config["recon_name"]
    version = _next_version(db, recon_name)
    valid_config["version"] = version

    provider = get_provider()
    cfg = models.ReconConfig(
        recon_name=recon_name,
        recon_type=valid_config.get("recon_type", "POSITION"),
        version=version,
        config_json=valid_config,
        english_summary=provider.summarize_config(valid_config),
        status="DRAFT",
        author_id=user["user_id"],
        origin="authoring",
    )
    db.add(cfg)
    db.flush()
    audit(db, actor_id=user["user_id"], action="config_authored", entity_type="recon_config",
          entity_id=cfg.id, after={"recon_name": recon_name, "version": version, "repairs": repairs})
    db.commit()
    db.refresh(cfg)
    return config_to_out(cfg, repairs)


@router.post("/{config_id}/submit", response_model=ConfigOut)
def submit_config(
    config_id: int,
    user: dict = Depends(require_role("MAKER")),
    db: Session = Depends(get_db),
):
    cfg = db.get(models.ReconConfig, config_id)
    if not cfg:
        raise HTTPException(status_code=404, detail="Config not found")
    if cfg.status != "DRAFT":
        raise HTTPException(status_code=400, detail=f"Only DRAFT configs can be submitted (is {cfg.status})")
    cfg.status = "PENDING_APPROVAL"
    audit(db, actor_id=user["user_id"], action="config_submitted", entity_type="recon_config",
          entity_id=cfg.id, after={"status": "PENDING_APPROVAL"})
    db.commit()
    db.refresh(cfg)
    return config_to_out(cfg)


@router.post("/{config_id}/approve", response_model=ConfigOut)
def approve_config(
    config_id: int,
    body: ConfigDecisionRequest,
    user: dict = Depends(require_role("CHECKER")),
    db: Session = Depends(get_db),
):
    cfg = db.get(models.ReconConfig, config_id)
    if not cfg:
        raise HTTPException(status_code=404, detail="Config not found")
    if cfg.status == "APPROVED":
        raise HTTPException(status_code=400, detail="Config is already approved")
    if cfg.author_id and user["user_id"] == cfg.author_id:
        raise HTTPException(status_code=403, detail="Maker cannot self-approve — pick a different reviewer")

    if not body.approved:
        cfg.status = "DRAFT"
        audit(db, actor_id=user["user_id"], action="config_rejected", entity_type="recon_config",
              entity_id=cfg.id, after={"status": "DRAFT", "notes": body.notes})
        db.commit()
        db.refresh(cfg)
        return config_to_out(cfg)

    # Supersede the prior APPROVED version of the same recon.
    prior = (
        db.query(models.ReconConfig)
        .filter(models.ReconConfig.recon_name == cfg.recon_name,
                models.ReconConfig.status == "APPROVED",
                models.ReconConfig.id != cfg.id)
        .all()
    )
    for p in prior:
        p.status = "SUPERSEDED"
        p.superseded_by = cfg.id

    cfg.status = "APPROVED"
    cfg.approver_id = user["user_id"]
    cfg.approved_at = datetime.now(timezone.utc)
    cfg_json = dict(cfg.config_json)
    cfg_json["status"] = "APPROVED"
    cfg.config_json = cfg_json
    audit(db, actor_id=user["user_id"], action="config_approved", entity_type="recon_config",
          entity_id=cfg.id, after={"status": "APPROVED", "version": cfg.version,
                                   "superseded": [p.id for p in prior]})
    db.commit()
    db.refresh(cfg)
    return config_to_out(cfg)


@router.get("/{config_id}", response_model=ConfigOut)
def get_config(config_id: int, user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    cfg = db.get(models.ReconConfig, config_id)
    if not cfg:
        raise HTTPException(status_code=404, detail="Config not found")
    return config_to_out(cfg)


@router.get("/{config_id}/versions", response_model=List[ConfigOut])
def config_versions(config_id: int, user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    cfg = db.get(models.ReconConfig, config_id)
    if not cfg:
        raise HTTPException(status_code=404, detail="Config not found")
    versions = (
        db.query(models.ReconConfig)
        .filter(models.ReconConfig.recon_name == cfg.recon_name)
        .order_by(models.ReconConfig.id)
        .all()
    )
    return [config_to_out(c) for c in versions]


@router.get("", response_model=List[ConfigOut])
def list_configs(
    recon_name: Optional[str] = None,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(models.ReconConfig)
    if recon_name:
        q = q.filter(models.ReconConfig.recon_name == recon_name)
    return [config_to_out(c) for c in q.order_by(models.ReconConfig.recon_name, models.ReconConfig.id).all()]
