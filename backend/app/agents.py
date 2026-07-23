"""Agent layer v2 (P7): SME analysis, Judge routing, Loop A pattern detection.

The deterministic classifier (engine/archetype) owns archetype / causal origin /
root-cause tree — the reproducible core. The SME agent wraps it with resolution
prose, resolution-memory few-shot (Loop B recall), and a refuse-to-classify gate
(<0.65). The Judge applies **code-enforced** routing bands (an LLM may recommend,
but code decides). Loop A detects systemic patterns across force-matched breaks
and proposes a config change — capping DATE_TOLERANCE at 5 days.

Everything here is deterministic by default (stub posture); a real LLM can enrich
the prose later without changing routing or classification.
"""
from __future__ import annotations

import re
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models
from .config import get_settings
from .engine.archetype import classify

settings = get_settings()

REFUSE_THRESHOLD = 0.65
DATE_TOLERANCE_CAP_DAYS = 5

# Autonomy routes.
STP_AUTO_RESOLVE = "STP_AUTO_RESOLVE"
MAKER_REVIEW_REQUIRED = "MAKER_REVIEW_REQUIRED"
ESCALATE_SENIOR = "ESCALATE_SENIOR"
REGULATORY_ESCALATION = "REGULATORY_ESCALATION"

RESOLUTION_TEMPLATES: Dict[str, str] = {
    "settlement_date_drift": "Confirm the settlement date with the counterparty; if this drift recurs, widen the date tolerance via Loop A.",
    "quantity_rounding": "Verify the quantity against the source booking; a sub-unit difference is usually an ETL rounding artefact — align rounding at source.",
    "fx_price_rounding": "Accept as an FX/price rounding artefact if within house tolerance; otherwise confirm the price source used on each side.",
    "one_to_many_split": "Link the split legs so the aggregate ties out; future splits will short-circuit via resolution memory.",
    "many_to_one_aggregate": "Confirm the aggregate booking corresponds to the individual legs and link them.",
    "nm_subset_group": "Investigate whether the group is a genuine subset settlement before matching; do not auto-resolve.",
    "missing_leg": "Chase the counterparty for the missing leg; escalate if it remains unposted beyond the next settlement cycle.",
    "duplicate_entry": "Investigate the duplicate posting with the source system and reverse the extra entry once confirmed.",
    "account_misbooking": "Contact the posting team to confirm the correct account and arrange a reclassification.",
    "emir_amount_dispute": "Escalate as an EMIR Article 15 valuation dispute; confirm the market value with the counterparty before filing.",
    "corporate_action_adjustment": "Apply the corporate-action ratio; treat as explained once the adjusted quantity ties out.",
    "cass_shortfall": "Top up the safeguarded client-money account to remove the shortfall and record the CASS resolution.",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --- Loop B recall ----------------------------------------------------------
def retrieve_similar_cases(
    db: Session, archetype: str, causal_origin: Optional[str], limit: int = 3
) -> List[Dict[str, Any]]:
    """Top matching resolution memories (few-shot); bumps usage_count/last_used_at."""
    q = select(models.ResolutionMemory).where(models.ResolutionMemory.archetype == archetype)
    if causal_origin:
        q = q.where(models.ResolutionMemory.causal_origin == causal_origin)
    rows = db.execute(
        q.order_by(
            models.ResolutionMemory.usage_count.desc(),
            models.ResolutionMemory.created_at.desc(),
        ).limit(limit)
    ).scalars().all()

    out: List[Dict[str, Any]] = []
    for r in rows:
        r.usage_count += 1
        r.last_used_at = _now()
        out.append(
            {
                "archetype": r.archetype,
                "causal_origin": r.causal_origin,
                "resolution": r.resolution,
                "confidence": r.confidence,
                "times_seen": r.times_seen,
            }
        )
    if rows:
        db.commit()
    return out


# --- SME agent --------------------------------------------------------------
def sme_analyze(brk: Dict[str, Any], db: Optional[Session] = None) -> Dict[str, Any]:
    base = classify(brk)
    archetype = base["archetype"]
    similar = (
        retrieve_similar_cases(db, archetype, base["causal_origin"]) if db is not None else []
    )
    refuse = base["confidence"] < REFUSE_THRESHOLD
    evidence = base["root_cause_tree"]["ai_diagnosis"]["evidence"]
    explanation = " ".join([base["label"] + "."] + evidence)

    return {
        **base,
        "explanation": explanation,
        "suggested_resolution": RESOLUTION_TEMPLATES.get(archetype, "Investigate manually with the source system."),
        "regulatory_narrative": brk.get("regulatory_narrative"),
        "refuse_to_classify": refuse,
        "refuse_reason": "Confidence below the 0.65 classification threshold" if refuse else None,
        "similar_cases": similar,
    }


# --- Judge agent (code-enforced routing) ------------------------------------
def judge_route(sme_result: Dict[str, Any], regulatory_escalation_required: bool = False) -> Dict[str, Any]:
    conf = float(sme_result.get("confidence", 0))
    threshold = settings.stp_threshold

    if regulatory_escalation_required:
        route = REGULATORY_ESCALATION
        rationale = "Regulatory escalation required — overrides autonomy routing."
    elif conf < REFUSE_THRESHOLD:
        route = ESCALATE_SENIOR
        rationale = f"Confidence {conf:.2f} below {REFUSE_THRESHOLD} — escalate to a senior reviewer."
    elif conf >= threshold:
        route = STP_AUTO_RESOLVE
        rationale = f"Confidence {conf:.2f} ≥ {threshold:.2f} — straight-through auto-resolve."
    else:
        route = MAKER_REVIEW_REQUIRED
        rationale = f"Confidence {conf:.2f} in the review band — route to a maker."

    return {
        "autonomy_route": route,
        "judge_confidence": conf,
        "routing_rationale": rationale,
        "regulatory_escalation_required": regulatory_escalation_required,
        "judge_agrees": not sme_result.get("refuse_to_classify", False),
    }


# --- Loop A v2 --------------------------------------------------------------
def _bump_minor(version: str) -> str:
    m = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", version or "1.0.0")
    if not m:
        return "1.1.0"
    return f"{m.group(1)}.{int(m.group(2)) + 1}.0"


def detect_loop_a_pattern(manual_matches: List[Dict[str, Any]], min_occurrences: int = 4) -> Optional[Dict[str, Any]]:
    """Detect a systemic pattern across force-matched breaks' deltas.

    Returns the strongest pattern (date drift, then quantity rounding) that
    reaches the occurrence threshold, else None.
    """
    date_deltas: List[int] = []
    qty_small = 0
    for mm in manual_matches:
        for key, val in (mm.get("deltas") or {}).items():
            if not isinstance(val, (int, float)):
                continue
            k = key.lower()
            if "date" in k:
                date_deltas.append(int(val))
            elif "quantity" in k and abs(val) < 2:
                qty_small += 1

    if date_deltas:
        delta_val, n = Counter(date_deltas).most_common(1)[0]
        if n >= min_occurrences:
            return {"pattern": "date_drift", "delta": int(delta_val), "count": n}
    if qty_small >= min_occurrences:
        return {"pattern": "quantity_rounding", "delta": 1, "count": qty_small}
    return None


def _widen_date_tolerance(config: Dict[str, Any], new_days: int) -> int:
    changed = 0
    for p in config.get("matching_waterfall", []):
        for rule in p.get("value_rules", []) or []:
            if rule.get("match_type") == "DATE_TOLERANCE" and int(rule.get("tolerance_days", 0)) < new_days:
                rule["tolerance_days"] = new_days
                changed += 1
    return changed


def propose_loop_a_change(current_config: Dict[str, Any], pattern: Dict[str, Any]) -> Dict[str, Any]:
    """Turn a detected pattern into a DRAFT config proposal (semver-bumped)."""
    cfg = deepcopy(current_config)
    cap_note: Optional[str] = None

    if pattern["pattern"] == "date_drift":
        observed = int(pattern["delta"])
        capped = min(observed, DATE_TOLERANCE_CAP_DAYS)
        if observed > DATE_TOLERANCE_CAP_DAYS:
            cap_note = f"Observed drift of {observed} days exceeds the {DATE_TOLERANCE_CAP_DAYS}-day cap; clamped to {capped}."
        _widen_date_tolerance(cfg, capped)
        rationale = (
            f"{pattern['count']} force-matched breaks showed a consistent {observed}-day settlement "
            f"drift. Proposing to widen DATE_TOLERANCE to {capped} day(s)."
        )
    elif pattern["pattern"] == "quantity_rounding":
        rationale = (
            f"{pattern['count']} force-matched breaks showed sub-unit quantity differences. "
            "Proposing a small quantity tolerance."
        )
    else:  # pragma: no cover - defensive
        rationale = "Systemic pattern detected."

    cfg["version"] = _bump_minor(current_config.get("version", "1.0.0"))
    cfg["status"] = "DRAFT"
    return {
        "pattern": pattern,
        "proposed_config": cfg,
        "rationale": rationale,
        "cap_note": cap_note,
    }
