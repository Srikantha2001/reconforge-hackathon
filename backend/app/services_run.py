"""Run orchestration v2 (P8): execute → persist → analyze → Loop A.

Ties the P3 engine, P6 EMIR screen, and P7 agents to the v2 persistence model.
``execute_run`` runs the deterministic engine and persists the Run, its Breaks
(open + explained), and the MatchLedger; then screens breaks for EMIR. The
break-analyze step runs the SME classifier + Judge routing over a run's open
breaks and persists the decision (auto-resolving the STP band). Loop A detects
systemic patterns from force-matched breaks and proposes a re-versioned config.
"""
from __future__ import annotations

import io
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import agents, models
from .config import get_settings
from .engine.runner import reconcile
from .services import audit
from .services_regulatory import screen_breaks_for_emir

settings = get_settings()
SEED_DIR = Path(__file__).resolve().parent.parent / "data"


def _dec(value: Any) -> Optional[Decimal]:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (ValueError, TypeError):
        return None


def read_csv_bytes(content: bytes) -> pd.DataFrame:
    return pd.read_csv(io.BytesIO(content))


def read_csv_path(path: str) -> pd.DataFrame:
    return pd.read_csv(path)


# --- Execute + persist ------------------------------------------------------
def execute_run(
    db: Session,
    *,
    config: models.ReconConfig,
    df_a: pd.DataFrame,
    df_b: pd.DataFrame,
    file_a_ref: Optional[str],
    file_b_ref: Optional[str],
    actor_id: str,
    client_id: Optional[str] = None,
    is_client_run: bool = False,
    run_date: Optional[str] = None,
) -> models.Run:
    run_date = run_date or date.today().isoformat()
    result = reconcile(df_a, df_b, config.config_json, run_date=run_date, data_dir=SEED_DIR)

    proof_a = result.position_proof.get("A", {})
    run = models.Run(
        config_id=config.id,
        config_version=config.version,
        file_a_ref=file_a_ref,
        file_b_ref=file_b_ref,
        matched_count=result.matched_count,
        break_count=result.break_count,
        total_a=result.total_a,
        total_b=result.total_b,
        match_rate=_dec(result.match_rate),
        position_proof_status=proof_a.get("status"),
        output_hash=result.output_hash,
        actor_id=str(actor_id),
        client_id=str(client_id) if client_id else None,
        is_client_run=is_client_run,
    )
    db.add(run)
    db.flush()

    open_breaks: List[models.Break] = []
    for b in result.breaks:
        brk = _persist_break(db, run.id, b, run_date)
        open_breaks.append(brk)
    for b in result.explained_breaks:
        # Explained breaks (e.g. corporate action) are recorded but not "open".
        brk = _persist_break(db, run.id, b, run_date, status="explained",
                             archetype="corporate_action_adjustment")

    for m in result.matches:
        db.add(
            models.MatchLedger(
                run_id=run.id,
                pass_number=m.get("pass_number") or 0,
                pass_name=m.get("pass_name") or "",
                match_type=m.get("match_type") or "",
                row_ids_a=",".join(m.get("row_ids_a", [])),
                row_ids_b=",".join(m.get("row_ids_b", [])),
                isin=m.get("isin"),
                currency=m.get("currency"),
                quantity_a=_dec(m.get("quantity_a")),
                quantity_b=_dec(m.get("quantity_b")),
                amount_a=_dec(m.get("amount_a")),
                amount_b=_dec(m.get("amount_b")),
                quantity_variance=_dec(m.get("quantity_variance")),
                amount_variance=_dec(m.get("amount_variance")),
            )
        )

    db.flush()
    # Post-run regulatory screen (P6) over the just-persisted open breaks.
    notifications = screen_breaks_for_emir(db, open_breaks, run_date=run_date)
    run.regulatory_escalation_count = len(notifications)

    audit(db, actor_id=str(actor_id), action="run_executed", entity_type="run", entity_id=run.id,
          after={"config_version": config.version, "matched": result.matched_count,
                 "breaks": result.break_count, "match_rate": result.match_rate,
                 "output_hash": result.output_hash, "regulatory": len(notifications)})
    db.flush()
    return run


def _persist_break(db, run_id, b, run_date, *, status="open", archetype=None) -> models.Break:
    from .engine.business_days import business_day_diff

    settlement = None
    if isinstance(b.get("row_a"), dict):
        settlement = b["row_a"].get("settlement_date")
    age = business_day_diff(settlement, run_date, set()) if settlement else 0

    brk = models.Break(
        run_id=run_id,
        break_key=b["break_key"],
        side=b.get("side"),
        row_a=b.get("row_a"),
        row_b=b.get("row_b"),
        failed_rules=b.get("failed_rules", []),
        deltas=b.get("deltas", {}),
        isin=b.get("isin"),
        currency=b.get("currency"),
        quantity_a=_dec(b.get("quantity_a")),
        quantity_b=_dec(b.get("quantity_b")),
        amount_a=_dec(b.get("amount_a")),
        amount_b=_dec(b.get("amount_b")),
        quantity_variance=_dec(b.get("quantity_variance")),
        amount_variance=_dec(b.get("amount_variance")),
        pass_that_failed=b.get("pass_that_failed"),
        archetype=archetype or b.get("archetype"),
        severity=b.get("severity", "medium"),
        age_business_days=age or 0,
        status=status,
    )
    db.add(brk)
    db.flush()
    return brk


def reproduce(db: Session, run: models.Run) -> Tuple[str, bool]:
    df_a = read_csv_path(run.file_a_ref)
    df_b = read_csv_path(run.file_b_ref)
    result = reconcile(df_a, df_b, run.config.config_json, data_dir=SEED_DIR)
    return result.output_hash, result.output_hash == run.output_hash


# --- Break analysis (SME + Judge) -------------------------------------------
def _break_to_dict(brk: models.Break) -> Dict[str, Any]:
    return {
        "break_key": brk.break_key,
        "side": brk.side,
        "isin": brk.isin,
        "currency": brk.currency,
        "row_a": brk.row_a,
        "row_b": brk.row_b,
        "failed_rules": brk.failed_rules or [],
        "deltas": brk.deltas or {},
        "archetype": brk.archetype,
        "quantity_a": float(brk.quantity_a) if brk.quantity_a is not None else None,
        "quantity_b": float(brk.quantity_b) if brk.quantity_b is not None else None,
        "amount_variance": float(brk.amount_variance) if brk.amount_variance is not None else None,
        "quantity_variance": float(brk.quantity_variance) if brk.quantity_variance is not None else None,
        "pass_that_failed": brk.pass_that_failed,
        "regulatory_narrative": brk.regulatory_narrative,
    }


def analyze_run_breaks(db: Session, run: models.Run, actor_id: str) -> List[Dict[str, Any]]:
    """SME classify + Judge route every open break; persist and auto-resolve STP."""
    breaks = db.execute(
        select(models.Break).where(models.Break.run_id == run.id, models.Break.status == "open")
    ).scalars().all()

    out: List[Dict[str, Any]] = []
    for brk in breaks:
        sme = agents.sme_analyze(_break_to_dict(brk), db=db)
        judge = agents.judge_route(sme, regulatory_escalation_required=brk.regulatory_escalation_required)

        brk.archetype = sme["archetype"]
        brk.causal_origin = sme["causal_origin"]
        brk.field_most_responsible = sme["field_most_responsible"]
        brk.root_cause_tree = sme["root_cause_tree"]
        brk.explanation = sme["explanation"]
        brk.suggested_resolution = sme["suggested_resolution"]
        brk.sme_confidence = sme["confidence"]
        brk.judge_confidence = judge["judge_confidence"]
        brk.judge_decision = judge["autonomy_route"]
        brk.autonomy_route = judge["autonomy_route"]

        route = judge["autonomy_route"]
        if route == agents.STP_AUTO_RESOLVE:
            brk.status = "RESOLVED_STP"
            _write_stp_memory(db, brk, sme)
        elif route == agents.REGULATORY_ESCALATION:
            brk.status = "PENDING_REGULATORY_ACTION"
        else:
            brk.status = "open"  # routed to a human (maker/senior)

        audit(db, actor_id=str(actor_id), action="break_analyzed", entity_type="break",
              entity_id=brk.id, after={"archetype": sme["archetype"], "route": route},
              agent_reasoning=judge["routing_rationale"], confidence=sme["confidence"])
        out.append({"break_id": brk.id, "sme": sme, "judge": judge})

    db.commit()
    return out


def _write_stp_memory(db: Session, brk: models.Break, sme: Dict[str, Any]) -> None:
    feature_key = f"{sme['archetype']}|{brk.side or ''}|STP_AUTO"
    existing = db.execute(
        select(models.ResolutionMemory).where(models.ResolutionMemory.feature_key == feature_key)
    ).scalar_one_or_none()
    if existing:
        existing.times_seen += 1
        return
    db.add(
        models.ResolutionMemory(
            feature_key=feature_key,
            feature_vector={"archetype": sme["archetype"], "side": brk.side},
            archetype=sme["archetype"],
            causal_origin=sme["causal_origin"],
            resolution=sme["suggested_resolution"],
            confidence=sme["confidence"],
            times_seen=1,
        )
    )


# --- Loop A v2 --------------------------------------------------------------
def loop_a_manual_matches(db: Session, run_id: int) -> List[Dict[str, Any]]:
    matches = db.execute(
        select(models.ManualMatch).where(models.ManualMatch.run_id == run_id)
    ).scalars().all()
    return [{"deltas": m.deltas or {}} for m in matches]


def loop_a_detect(db: Session, run_id: int) -> Optional[Dict[str, Any]]:
    return agents.detect_loop_a_pattern(loop_a_manual_matches(db, run_id))


def loop_a_propose(db: Session, run: models.Run, actor_id: str) -> Optional[Dict[str, Any]]:
    pattern = loop_a_detect(db, run.id)
    if not pattern:
        return None
    proposal = agents.propose_loop_a_change(run.config.config_json, pattern)

    new_config = models.ReconConfig(
        recon_name=run.config.recon_name,
        recon_type=run.config.recon_type,
        version=proposal["proposed_config"]["version"],
        config_json=proposal["proposed_config"],
        english_summary=f"Loop A re-version: {proposal['rationale']}",
        status="PENDING_APPROVAL",
        author_id=str(actor_id),
        parent_id=run.config.id,
        origin="loop_a",
    )
    db.add(new_config)
    db.flush()

    suggestion = models.LoopASuggestion(
        run_id=run.id,
        pattern_detected=proposal["rationale"],
        manual_match_count=pattern["count"],
        proposed_config_change=proposal["proposed_config"],
        status="PENDING",
        resulting_config_id=new_config.id,
    )
    db.add(suggestion)
    audit(db, actor_id=str(actor_id), action="loop_a_proposed", entity_type="recon_config",
          entity_id=new_config.id, after={"pattern": pattern, "rationale": proposal["rationale"],
                                          "cap_note": proposal["cap_note"]})
    db.commit()
    db.refresh(new_config)
    return {"new_config": new_config, "rationale": proposal["rationale"], "cap_note": proposal["cap_note"]}


def loop_a_what_if(db: Session, run: models.Run, candidate: models.ReconConfig) -> Dict[str, Any]:
    df_a = read_csv_path(run.file_a_ref)
    df_b = read_csv_path(run.file_b_ref)
    current = reconcile(df_a, df_b, run.config.config_json, data_dir=SEED_DIR)
    cand = reconcile(df_a, df_b, candidate.config_json, data_dir=SEED_DIR)

    def _keys(res):
        return {f"{m['isin']}:{m['pass_number']}" for m in res.matches}

    cur_keys, cand_keys = _keys(current), _keys(cand)
    return {
        "current_match_rate": current.match_rate,
        "candidate_match_rate": cand.match_rate,
        "current_matched": current.matched_count,
        "candidate_matched": cand.matched_count,
        "newly_matched_keys": sorted(cand_keys - cur_keys),
        "newly_broken_keys": sorted(cur_keys - cand_keys),
    }
