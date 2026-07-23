"""Regulatory services (P6): EMIR Article 15 + CASS 7A (CSDR minimal).

EMIR: a reconciliation break whose EUR market-value exceeds the reporting
threshold and which has stayed unresolved beyond the day limit is flagged for
escalation and gets a DRAFT notification. Draft narratives are generated
deterministically (the offline stub posture — a real LLM can enrich later);
nothing is auto-filed — a CHECKER/DSI approves DRAFT -> FILED.

CASS: a daily comparison of client liability vs safeguarded funds per account.
A shortfall above the threshold is escalated and captured in a hashed
resolution pack.

Amounts are EUR-converted via fx_rates and formatted deterministically so the
resolution-pack hash is stable (Law 4 posture applied to regulatory output).
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models
from .config import get_settings
from .engine.business_days import business_day_diff, parse_holidays
from .services import audit

settings = get_settings()
SEED_DIR = Path(__file__).resolve().parent.parent / "data"


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --- Aux loaders ------------------------------------------------------------
def _read_aux(name: str, aux_data: Optional[Dict[str, pd.DataFrame]], alias: str) -> Optional[pd.DataFrame]:
    if aux_data and alias in aux_data:
        return aux_data[alias]
    path = SEED_DIR / name
    return pd.read_csv(path) if path.exists() else None


def _fx_rates(aux_data=None) -> Dict[str, float]:
    df = _read_aux("fx_rates.csv", aux_data, "fx_rates")
    if df is None:
        return {"EUR": 1.0}
    return {str(r["currency"]): float(r["rate_to_eur"]) for _, r in df.iterrows()}


def _eur_amount(amount: Any, currency: Optional[str], fx: Dict[str, float]) -> float:
    rate = fx.get(str(currency or "EUR"), 1.0)
    return round(abs(float(amount or 0)) * rate, 2)


# --- EMIR -------------------------------------------------------------------
def _break_age_days(brk: models.Break, run_date: Optional[str], holidays) -> int:
    if brk.age_business_days and brk.age_business_days > 0:
        return brk.age_business_days
    settlement = None
    if isinstance(brk.row_a, dict):
        settlement = brk.row_a.get("settlement_date") or brk.row_a.get("posting_date")
    if settlement and run_date:
        diff = business_day_diff(settlement, run_date, holidays.get("TARGET2", set()))
        return diff or 0
    return 0


def _emir_narrative(brk, eur_amount, age, authority) -> str:
    return (
        f"EMIR Article 15 dispute notification (DRAFT). Reconciliation break "
        f"{brk.break_key} on instrument {brk.isin or 'n/a'} shows a market-value "
        f"discrepancy of EUR {eur_amount:,.2f}, exceeding the "
        f"EUR {settings.emir_amount_threshold_eur:,.2f} reporting threshold, and "
        f"has remained unresolved for {age} business day(s) (limit "
        f"{settings.emir_days_threshold}). Competent authority: {authority}. "
        f"Prepared for review — not filed."
    )


def screen_breaks_for_emir(
    db: Session,
    breaks: List[models.Break],
    *,
    run_date: Optional[str] = None,
    aux_data: Optional[Dict[str, pd.DataFrame]] = None,
    competent_authority: str = "BaFin",
) -> List[models.RegulatoryNotification]:
    """Flag qualifying breaks + create DRAFT EMIR notifications.

    Called by the run flow after breaks are persisted (P8); driven directly by
    tests in P6. A break qualifies when its EUR market value exceeds the amount
    threshold AND its age exceeds the day threshold.
    """
    fx = _fx_rates(aux_data)
    holidays_df = _read_aux("market_holidays.csv", aux_data, "market_holidays")
    holidays = parse_holidays(holidays_df.to_dict("records")) if holidays_df is not None else {}

    created: List[models.RegulatoryNotification] = []
    for brk in breaks:
        eur = _eur_amount(brk.amount_a, brk.currency, fx)
        age = _break_age_days(brk, run_date, holidays)
        if eur > settings.emir_amount_threshold_eur and age > settings.emir_days_threshold:
            brk.regulatory_escalation_required = True
            narrative = _emir_narrative(brk, eur, age, competent_authority)
            brk.regulatory_narrative = narrative
            notif = models.RegulatoryNotification(
                break_id=brk.id,
                regime="EMIR_ARTICLE_15",
                competent_authority=competent_authority,
                notification_draft=narrative,
                dispute_amount=Decimal(str(eur)),
                dispute_days=age,
                status="DRAFT",
            )
            db.add(notif)
            db.flush()
            audit(db, actor_id=None, action="emir_notification_drafted",
                  entity_type="regulatory_notification", entity_id=notif.id,
                  after={"break_id": brk.id, "eur_amount": eur, "age_days": age})
            created.append(notif)
    if created:
        db.commit()
    return created


def list_emir_notifications(db: Session, status: str = "DRAFT") -> List[models.RegulatoryNotification]:
    return db.execute(
        select(models.RegulatoryNotification)
        .where(models.RegulatoryNotification.regime == "EMIR_ARTICLE_15")
        .where(models.RegulatoryNotification.status == status)
        .order_by(models.RegulatoryNotification.created_at.desc())
    ).scalars().all()


def approve_emir_notification(db: Session, notification_id: int, approver_id: str) -> models.RegulatoryNotification:
    notif = db.get(models.RegulatoryNotification, notification_id)
    if not notif:
        raise HTTPException(status_code=404, detail="Notification not found")
    if notif.status == "FILED":
        raise HTTPException(status_code=400, detail="Notification already filed")
    # DRAFT -> PENDING_APPROVAL -> FILED (recorded as a single approve action).
    notif.status = "FILED"
    notif.approved_by = str(approver_id)
    notif.approved_at = _now()
    notif.filed_at = _now()
    audit(db, actor_id=str(approver_id), action="emir_notification_filed",
          entity_type="regulatory_notification", entity_id=notif.id,
          before={"status": "DRAFT"}, after={"status": "FILED"})
    db.commit()
    db.refresh(notif)
    return notif


# --- CASS 7A ----------------------------------------------------------------
def _cass_breakdown(aux_data=None) -> Dict[str, Any]:
    df = _read_aux("cass_safeguarded.csv", aux_data, "cass_safeguarded")
    if df is None:
        return {"accounts": [], "liability_total": 0.0, "safeguarded_total": 0.0, "shortfall": 0.0}
    accounts = []
    liability_total = 0.0
    safeguarded_total = 0.0
    for _, r in df.iterrows():
        liability = round(float(r["client_liability_eur"]), 2)
        safeguarded = round(float(r["safeguarded_amount_eur"]), 2)
        shortfall = round(liability - safeguarded, 2)
        accounts.append(
            {
                "client_account": str(r["client_account"]),
                "fund_id": str(r.get("fund_id", "")),
                "client_liability_eur": liability,
                "safeguarded_amount_eur": safeguarded,
                "shortfall_eur": shortfall,
            }
        )
        liability_total += liability
        safeguarded_total += safeguarded
    return {
        "accounts": accounts,
        "liability_total": round(liability_total, 2),
        "safeguarded_total": round(safeguarded_total, 2),
        "shortfall": round(liability_total - safeguarded_total, 2),
    }


def cass_daily(db: Session, date: str, aux_data=None) -> models.CassReconciliation:
    """Return (creating if absent) the CASS reconciliation for a date."""
    existing = db.execute(
        select(models.CassReconciliation).where(models.CassReconciliation.reconciliation_date == date)
    ).scalar_one_or_none()
    if existing:
        return existing

    b = _cass_breakdown(aux_data)
    shortfall = b["shortfall"]
    status = "SHORTFALL_DETECTED" if shortfall > settings.cass_shortfall_threshold_eur else "NIL"
    pack_hash = _resolution_pack_hash(date, b, status)

    recon = models.CassReconciliation(
        reconciliation_date=date,
        client_liability_total=Decimal(str(b["liability_total"])),
        safeguarded_funds_total=Decimal(str(b["safeguarded_total"])),
        shortfall_amount=Decimal(str(shortfall)),
        shortfall_status=status,
        resolution_pack_hash=pack_hash,
    )
    db.add(recon)
    audit(db, actor_id=None, action="cass_reconciliation_run",
          entity_type="cass_reconciliation", entity_id=None,
          after={"date": date, "shortfall": shortfall, "status": status})
    db.commit()
    db.refresh(recon)
    return recon


def _resolution_pack_dict(date: str, breakdown: Dict[str, Any], status: str) -> Dict[str, Any]:
    return {
        "regime": "CASS_7A",
        "reconciliation_date": date,
        "accounts": breakdown["accounts"],
        "client_liability_total_eur": breakdown["liability_total"],
        "safeguarded_funds_total_eur": breakdown["safeguarded_total"],
        "shortfall_eur": breakdown["shortfall"],
        "shortfall_status": status,
    }


def _resolution_pack_hash(date: str, breakdown: Dict[str, Any], status: str) -> str:
    pack = _resolution_pack_dict(date, breakdown, status)
    blob = json.dumps(pack, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def cass_resolution_pack(db: Session, date: str, aux_data=None) -> Dict[str, Any]:
    b = _cass_breakdown(aux_data)
    status = "SHORTFALL_DETECTED" if b["shortfall"] > settings.cass_shortfall_threshold_eur else "NIL"
    pack = _resolution_pack_dict(date, b, status)
    pack["document_hash"] = _resolution_pack_hash(date, b, status)
    pack["generated_at"] = _now().isoformat()
    return pack
