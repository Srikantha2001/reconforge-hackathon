"""Governance service (P5): break actions, maker-checker, journal entries.

Makers propose one of four actions on an open break (FORCE_MATCH, WRITE_OFF,
INVESTIGATE, AWAIT_COUNTERPARTY); a *different* checker approves or rejects.
Approving an accounting action (WRITE_OFF / FORCE_MATCH) resolves the break and
generates a journal entry — which is EXPORT-ONLY and never auto-posted (Law 9)
— plus writes resolution memory; FORCE_MATCH additionally records a manual-match
signal so Loop A keeps learning.

Laws enforced here:
- maker != checker: checked at the API layer (clean 400) AND backstopped by the
  DB CheckConstraint on governance_action (Law 5).
- Journal entries are never posted, only recorded for export (Law 9).
- Audit log is append-only: every transition writes one row (Law 6).

Autonomy: a WRITE_OFF below ``write_off_auto_approve_below_eur`` is auto-approved
at submission (checker_id sentinel ``STP_AUTO``, distinct from any numeric user
id so the maker!=checker constraint still holds); a WRITE_OFF above
``write_off_dual_checker_above_eur`` is blocked for a single checker.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models
from .config import get_settings
from .services import audit

settings = get_settings()

ACTION_TYPES = ("FORCE_MATCH", "WRITE_OFF", "INVESTIGATE", "AWAIT_COUNTERPARTY")
ACCOUNTING_ACTIONS = ("WRITE_OFF", "FORCE_MATCH")  # resolve the break + post a journal entry
STP_AUTO = "STP_AUTO"  # checker sentinel for auto-approved small write-offs


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """SQLite hands back naive datetimes; treat them as UTC for comparisons."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _break_amount(brk: models.Break) -> float:
    return abs(float(brk.amount_a or 0))


def _account_of(row: Optional[Dict[str, Any]]) -> str:
    if isinstance(row, dict):
        return str(row.get("account_id") or row.get("account") or "SUSPENSE")
    return "SUSPENSE"


# --- Maker ------------------------------------------------------------------
def maker_submit(
    db: Session, *, break_id: int, maker_id: str, action_type: str, notes: Optional[str]
) -> Dict[str, Any]:
    if action_type not in ACTION_TYPES:
        raise HTTPException(status_code=400, detail=f"Unknown action_type '{action_type}'")

    brk = db.get(models.Break, break_id)
    if not brk:
        raise HTTPException(status_code=404, detail="Break not found")
    if brk.status != "open":
        raise HTTPException(status_code=400, detail=f"Break is not open (status={brk.status})")

    action = models.GovernanceAction(
        break_id=break_id,
        action_type=action_type,
        maker_id=str(maker_id),
        status="PENDING",
        maker_notes=notes,
        expires_at=_now() + timedelta(hours=settings.pending_approval_expiry_hours),
    )
    db.add(action)
    brk.status = "PENDING_CHECKER_APPROVAL"
    db.flush()

    audit(
        db, actor_id=str(maker_id), action="governance_maker_submit",
        entity_type="governance_action", entity_id=action.id,
        after={"break_id": break_id, "action_type": action_type, "status": "PENDING"},
    )

    # Autonomy: auto-approve a small write-off without waiting for a checker.
    journal: Optional[models.JournalEntry] = None
    if action_type == "WRITE_OFF" and _break_amount(brk) < settings.write_off_auto_approve_below:
        journal = _resolve(db, action, brk, checker_id=STP_AUTO, notes="STP auto-approved", auto=True)

    db.commit()
    db.refresh(action)
    return {"action": action, "journal_entry": journal}


# --- Checker ----------------------------------------------------------------
def checker_approve(
    db: Session, *, action_id: int, checker_id: str, approved: bool, notes: Optional[str]
) -> Dict[str, Any]:
    action = db.get(models.GovernanceAction, action_id)
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")
    if action.status != "PENDING":
        raise HTTPException(status_code=400, detail=f"Action is not pending (status={action.status})")

    brk = db.get(models.Break, action.break_id)

    # Expiry check.
    if action.expires_at and _as_utc(action.expires_at) < _now():
        action.status = "EXPIRED"
        action.decided_at = _now()
        if brk:
            brk.status = "open"
        audit(db, actor_id=str(checker_id), action="governance_expired",
              entity_type="governance_action", entity_id=action.id)
        db.commit()
        raise HTTPException(status_code=400, detail="Action has expired")

    # maker != checker (Law 5) — clean 400 before the DB constraint would fire.
    if str(checker_id) == str(action.maker_id):
        raise HTTPException(status_code=400, detail="Maker cannot approve their own submission")

    if not approved:
        action.status = "REJECTED"
        action.checker_id = str(checker_id)
        action.checker_notes = notes
        action.rejection_reason = notes
        action.decided_at = _now()
        if brk:
            brk.status = "open"
        audit(db, actor_id=str(checker_id), action="governance_checker_reject",
              entity_type="governance_action", entity_id=action.id,
              after={"status": "REJECTED", "reason": notes})
        db.commit()
        return {"status": "REJECTED", "journal_entry": None}

    # Approve: enforce the single-checker write-off ceiling.
    if action.action_type == "WRITE_OFF" and _break_amount(brk) > settings.write_off_dual_checker_above:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Write-off of {_break_amount(brk):.2f} exceeds the single-checker limit "
                f"({settings.write_off_dual_checker_above:.2f}); requires a second checker"
            ),
        )

    journal = _resolve(db, action, brk, checker_id=str(checker_id), notes=notes)
    db.commit()
    return {"status": action.status, "journal_entry": journal}


# --- Resolution (shared by approve + auto-approve) --------------------------
def _resolve(
    db: Session,
    action: models.GovernanceAction,
    brk: models.Break,
    *,
    checker_id: str,
    notes: Optional[str],
    auto: bool = False,
) -> Optional[models.JournalEntry]:
    action.status = "APPROVED"
    action.checker_id = str(checker_id)
    action.checker_notes = notes
    action.decided_at = _now()

    journal: Optional[models.JournalEntry] = None
    if action.action_type in ACCOUNTING_ACTIONS:
        brk.status = "RESOLVED_APPROVED"
        journal = _generate_journal_entry(db, action, brk, approved_by=str(checker_id))
        _write_resolution_memory(db, brk, action)
        if action.action_type == "FORCE_MATCH":
            _write_manual_match(db, brk, actor_id=str(checker_id))
    else:
        # INVESTIGATE / AWAIT_COUNTERPARTY: workflow decision recorded; the
        # break stays open pending the ongoing action.
        brk.status = "open"

    audit(
        db,
        actor_id=str(checker_id),
        action="governance_auto_approve" if auto else "governance_checker_approve",
        entity_type="governance_action",
        entity_id=action.id,
        after={"status": "APPROVED", "action_type": action.action_type, "break_status": brk.status},
    )
    db.flush()
    return journal


def _generate_journal_entry(
    db: Session, action: models.GovernanceAction, brk: models.Break, approved_by: str
) -> models.JournalEntry:
    """Create an EXPORT-ONLY journal entry (Law 9 — never auto-posted)."""
    amount = Decimal(str(_break_amount(brk)))
    currency = brk.currency or "EUR"
    account = _account_of(brk.row_a) if brk.row_a else _account_of(brk.row_b)
    timestamp = _now().isoformat()
    audit_reference = hashlib.sha256(f"{action.id}|{approved_by}|{timestamp}".encode("utf-8")).hexdigest()

    if action.action_type == "WRITE_OFF":
        entry_type, debit, credit = "WRITE_OFF", "RECON_WRITE_OFF_EXPENSE", account
    else:  # FORCE_MATCH
        entry_type, debit, credit = "FORCE_MATCH_ADJUSTMENT", account, _account_of(brk.row_b)

    journal = models.JournalEntry(
        governance_action_id=action.id,
        break_id=brk.id,
        entry_type=entry_type,
        debit_account=debit,
        credit_account=credit,
        quantity=Decimal(str(abs(float(brk.quantity_a or 0)))),
        amount=amount,
        currency=currency,
        isin=brk.isin,
        narrative=(
            f"{action.action_type} of break {brk.break_key} ({brk.isin or 'n/a'}) "
            f"for {amount} {currency}. Export-only; not auto-posted."
        ),
        approved_by=str(approved_by),
        audit_reference=audit_reference,
    )
    db.add(journal)
    db.flush()
    return journal


def _write_resolution_memory(db: Session, brk: models.Break, action: models.GovernanceAction) -> None:
    archetype = brk.archetype or "unknown"
    feature_key = f"{archetype}|{brk.side or ''}|{action.action_type}"
    existing = db.execute(
        select(models.ResolutionMemory).where(models.ResolutionMemory.feature_key == feature_key)
    ).scalar_one_or_none()
    if existing:
        existing.times_seen += 1
        return
    db.add(
        models.ResolutionMemory(
            feature_key=feature_key,
            feature_vector={
                "archetype": archetype,
                "side": brk.side,
                "action_type": action.action_type,
                "isin": brk.isin,
            },
            archetype=archetype,
            causal_origin=brk.causal_origin,
            resolution=f"Resolved via {action.action_type} (maker-checker approved).",
            confidence=0.9,
            times_seen=1,
        )
    )


def _write_manual_match(db: Session, brk: models.Break, actor_id: str) -> None:
    """FORCE_MATCH doubles as a manual-match signal for Loop A."""
    db.add(
        models.ManualMatch(
            run_id=brk.run_id,
            break_id=brk.id,
            row_a=brk.row_a,
            row_b=brk.row_b,
            deltas=brk.deltas,
            actor_id=str(actor_id),
        )
    )


# --- Expiry sweep -----------------------------------------------------------
def expire_pending_actions(db: Session) -> int:
    """Flip expired PENDING actions to EXPIRED and reopen their breaks."""
    now = _now()
    pending = db.execute(
        select(models.GovernanceAction).where(models.GovernanceAction.status == "PENDING")
    ).scalars().all()
    count = 0
    for action in pending:
        if action.expires_at and _as_utc(action.expires_at) < now:
            action.status = "EXPIRED"
            action.decided_at = now
            brk = db.get(models.Break, action.break_id)
            if brk:
                brk.status = "open"
            audit(db, actor_id=None, action="governance_expired",
                  entity_type="governance_action", entity_id=action.id)
            count += 1
    if count:
        db.commit()
    return count


def list_pending(db: Session) -> list:
    """PENDING actions with computed time_remaining_seconds (after expiry sweep)."""
    expire_pending_actions(db)
    now = _now()
    actions = db.execute(
        select(models.GovernanceAction)
        .where(models.GovernanceAction.status == "PENDING")
        .order_by(models.GovernanceAction.submitted_at.desc())
    ).scalars().all()
    out = []
    for a in actions:
        remaining = 0
        if a.expires_at:
            remaining = max(0, int((_as_utc(a.expires_at) - now).total_seconds()))
        out.append((a, remaining))
    return out
