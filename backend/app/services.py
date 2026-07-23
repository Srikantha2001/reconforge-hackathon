"""Shared service helpers: audit writes and CSV/file I/O.

The v1 run/advise/loop orchestration that used to live here was superseded in
P8 by ``services_run`` (run execute/analyze/Loop A), ``services_governance``
(P5), and ``services_regulatory`` (P6). This module now holds only the small
helpers those services and the routers share.
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd
from sqlalchemy.orm import Session

from . import models


def audit(
    db: Session,
    *,
    actor_id: Optional[str],
    action: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[Any] = None,
    before: Optional[Dict[str, Any]] = None,
    after: Optional[Dict[str, Any]] = None,
    agent_reasoning: Optional[str] = None,
    confidence: Optional[float] = None,
) -> models.AuditLog:
    """Append one audit row (never updated/deleted — Law 6). Caller commits."""
    entry = models.AuditLog(
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        before=before,
        after=after,
        agent_reasoning=agent_reasoning,
        confidence=confidence,
    )
    db.add(entry)
    return entry


def read_csv_bytes(content: bytes) -> pd.DataFrame:
    return pd.read_csv(io.BytesIO(content))


def read_csv_path(path: str) -> pd.DataFrame:
    return pd.read_csv(path)


def save_bytes(content: bytes, dest_dir: Path, filename: str) -> str:
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / filename
    dest.write_bytes(content)
    return str(dest)
