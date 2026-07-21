from typing import List, Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models
from ..db import get_db
from ..schemas import AuditLogOut

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("", response_model=List[AuditLogOut])
def list_audit(
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    limit: int = 200,
    db: Session = Depends(get_db),
):
    q = db.query(models.AuditLog)
    if entity_type:
        q = q.filter(models.AuditLog.entity_type == entity_type)
    if entity_id:
        q = q.filter(models.AuditLog.entity_id == str(entity_id))
    return q.order_by(models.AuditLog.timestamp.desc()).limit(limit).all()
