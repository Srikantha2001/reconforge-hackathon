from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models
from ..actors import is_valid_actor
from ..config_schema import ConfigValidationError, validate_and_repair
from ..db import get_db
from ..llm import get_provider
from ..schemas import (
    ApproveConfigRequest,
    AuthorConfigRequest,
    ConfigOut,
    EditConfigRequest,
)
from ..services import audit

router = APIRouter(prefix="/api/configs", tags=["configs"])


def config_to_out(cfg: models.ReconConfig, repairs: Optional[List[str]] = None) -> ConfigOut:
    out = ConfigOut.model_validate(cfg)
    out.repairs_applied = repairs or []
    return out


def _require_actor(actor_id: str) -> None:
    if not is_valid_actor(actor_id):
        raise HTTPException(status_code=400, detail=f"Unknown actor_id '{actor_id}'")


@router.post("/author", response_model=ConfigOut)
def author_config(body: AuthorConfigRequest, db: Session = Depends(get_db)):
    _require_actor(body.actor_id)
    provider = get_provider()

    raw_config = provider.author_config(body.nl_description, body.columns_a, body.columns_b)
    if body.recon_name_hint:
        raw_config["recon_name"] = body.recon_name_hint

    try:
        valid_config, repairs = validate_and_repair(raw_config)
    except ConfigValidationError as e:
        raise HTTPException(status_code=422, detail={"message": "Config invalid even after repair", "errors": e.errors})

    existing_max = (
        db.query(models.ReconConfig)
        .filter(models.ReconConfig.recon_name == valid_config["recon_name"])
        .order_by(models.ReconConfig.version.desc())
        .first()
    )
    version = (existing_max.version + 1) if existing_max else 1

    summary = provider.summarize_config(valid_config)

    cfg = models.ReconConfig(
        recon_name=valid_config["recon_name"],
        version=version,
        config_json=valid_config,
        english_summary=summary,
        status="draft",
        author_id=body.actor_id,
        origin="authoring",
    )
    db.add(cfg)
    db.flush()

    audit(
        db,
        actor_id=body.actor_id,
        action="config_authored",
        entity_type="recon_config",
        entity_id=cfg.id,
        after={"config": valid_config, "repairs": repairs},
    )
    db.commit()
    db.refresh(cfg)
    return config_to_out(cfg, repairs)


@router.get("/{config_id}", response_model=ConfigOut)
def get_config(config_id: int, db: Session = Depends(get_db)):
    cfg = db.get(models.ReconConfig, config_id)
    if not cfg:
        raise HTTPException(status_code=404, detail="Config not found")
    return config_to_out(cfg)


@router.get("", response_model=List[ConfigOut])
def list_configs(recon_name: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(models.ReconConfig)
    if recon_name:
        q = q.filter(models.ReconConfig.recon_name == recon_name)
    configs = q.order_by(models.ReconConfig.recon_name, models.ReconConfig.version).all()
    return [config_to_out(c) for c in configs]


@router.post("/{config_id}/edit", response_model=ConfigOut)
def edit_config(config_id: int, body: EditConfigRequest, db: Session = Depends(get_db)):
    _require_actor(body.actor_id)
    cfg = db.get(models.ReconConfig, config_id)
    if not cfg:
        raise HTTPException(status_code=404, detail="Config not found")
    if cfg.status != "draft":
        raise HTTPException(status_code=400, detail="Only draft configs can be edited; approved configs are re-versioned instead")

    try:
        valid_config, repairs = validate_and_repair(body.config_json)
    except ConfigValidationError as e:
        raise HTTPException(status_code=422, detail={"message": "Config invalid even after repair", "errors": e.errors})

    before = cfg.config_json
    cfg.config_json = valid_config
    provider = get_provider()
    cfg.english_summary = provider.summarize_config(valid_config)

    audit(
        db,
        actor_id=body.actor_id,
        action="config_edited",
        entity_type="recon_config",
        entity_id=cfg.id,
        before={"config": before},
        after={"config": valid_config, "repairs": repairs},
    )
    db.commit()
    db.refresh(cfg)
    return config_to_out(cfg, repairs)


@router.post("/{config_id}/approve", response_model=ConfigOut)
def approve_config(config_id: int, body: ApproveConfigRequest, db: Session = Depends(get_db)):
    _require_actor(body.actor_id)
    cfg = db.get(models.ReconConfig, config_id)
    if not cfg:
        raise HTTPException(status_code=404, detail="Config not found")
    if cfg.status == "approved":
        raise HTTPException(status_code=400, detail="Config is already approved")
    if cfg.author_id and body.actor_id == cfg.author_id:
        raise HTTPException(status_code=403, detail="Maker cannot self-approve — pick a different reviewer")

    before_status = cfg.status
    cfg.status = "approved"
    cfg.approver_id = body.actor_id
    cfg.approved_at = datetime.now(timezone.utc)

    audit(
        db,
        actor_id=body.actor_id,
        action="config_approved",
        entity_type="recon_config",
        entity_id=cfg.id,
        before={"status": before_status},
        after={"status": "approved", "approver_id": body.actor_id, "version": cfg.version},
    )
    db.commit()
    db.refresh(cfg)
    return config_to_out(cfg)
