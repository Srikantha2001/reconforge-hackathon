"""Deterministic break classifier v2 (P7) — 12 archetypes, 9 causal origins.

Pure function of a break dict (as produced by ``runner.reconcile``): maps
pass/side/failed-rules/deltas to one of 12 archetypes, a causal origin, the
most-responsible field, a confidence, and a 3-layer root-cause tree
(data_layer / rule_that_failed / ai_diagnosis). No LLM, no DB — this is the
"no-LLM fallback" the SME agent builds on, and it keeps runs reproducible.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# --- Taxonomy ---------------------------------------------------------------
ARCHETYPES = (
    "settlement_date_drift",
    "quantity_rounding",
    "fx_price_rounding",
    "one_to_many_split",
    "many_to_one_aggregate",
    "nm_subset_group",
    "missing_leg",
    "duplicate_entry",
    "account_misbooking",
    "emir_amount_dispute",
    "corporate_action_adjustment",
    "cass_shortfall",
)

ARCHETYPE_LABELS: Dict[str, str] = {
    "settlement_date_drift": "Settlement date drift",
    "quantity_rounding": "Quantity rounding",
    "fx_price_rounding": "FX / price rounding",
    "one_to_many_split": "One-to-many split settlement",
    "many_to_one_aggregate": "Many-to-one aggregate",
    "nm_subset_group": "N-to-M subset group",
    "missing_leg": "Missing counterparty leg",
    "duplicate_entry": "Duplicate entry",
    "account_misbooking": "Account misbooking",
    "emir_amount_dispute": "EMIR market-value dispute",
    "corporate_action_adjustment": "Corporate action adjustment",
    "cass_shortfall": "CASS safeguarding shortfall",
}

CAUSAL_ORIGINS = (
    "SETTLEMENT_TIMING_LAG",
    "UPSTREAM_ETL_TRUNCATION",
    "COUNTERPARTY_FEE_DEDUCTION",
    "LEGAL_ENTITY_MISBOOKING",
    "FX_RATE_SOURCE_DIVERGENCE",
    "PARTIAL_SETTLEMENT",
    "CORPORATE_ACTION_PROCESSING_LAG",
    "PRICING_SOURCE_MISMATCH",
    "SYSTEM_REPLAY",
)

# Per-archetype defaults: (causal_origin, confidence).
_META: Dict[str, tuple] = {
    "settlement_date_drift": ("SETTLEMENT_TIMING_LAG", 0.85),
    "quantity_rounding": ("UPSTREAM_ETL_TRUNCATION", 0.70),
    "fx_price_rounding": ("FX_RATE_SOURCE_DIVERGENCE", 0.72),
    "one_to_many_split": ("PARTIAL_SETTLEMENT", 0.80),
    "many_to_one_aggregate": ("PARTIAL_SETTLEMENT", 0.80),
    "nm_subset_group": ("PARTIAL_SETTLEMENT", 0.75),
    "missing_leg": ("SETTLEMENT_TIMING_LAG", 0.60),
    "duplicate_entry": ("SYSTEM_REPLAY", 0.80),
    "account_misbooking": ("LEGAL_ENTITY_MISBOOKING", 0.80),
    "emir_amount_dispute": ("PRICING_SOURCE_MISMATCH", 0.90),
    "corporate_action_adjustment": ("CORPORATE_ACTION_PROCESSING_LAG", 0.90),
    "cass_shortfall": ("COUNTERPARTY_FEE_DEDUCTION", 0.85),
}

# A market-value delta above this is a genuine dispute (EMIR-scale); below it a
# rounding artefact. Chosen well above the pass-3 rounding guard (5.0).
_MV_DISPUTE_THRESHOLD = 100.0
_QTY_ROUNDING_THRESHOLD = 2.0


def _first_failed(failed_rules: List[Dict[str, Any]], needle: str) -> Optional[Dict[str, Any]]:
    for r in failed_rules or []:
        field = f"{r.get('field_a', '')}".lower()
        if needle in field:
            return r
    return None


def _num(value: Any) -> float:
    try:
        v = float(value)
        return 0.0 if v != v else v
    except (TypeError, ValueError):
        return 0.0


def _result(archetype: str, field: str, brk: Dict[str, Any], *, confidence: Optional[float] = None,
            evidence: Optional[List[str]] = None, alternative: str = "") -> Dict[str, Any]:
    causal, base_conf = _META[archetype]
    conf = base_conf if confidence is None else confidence
    return {
        "archetype": archetype,
        "label": ARCHETYPE_LABELS[archetype],
        "causal_origin": causal,
        "field_most_responsible": field,
        "confidence": round(conf, 3),
        "root_cause_tree": _root_cause_tree(archetype, field, brk, evidence or [], alternative),
    }


def _root_cause_tree(archetype, field, brk, evidence, alternative) -> Dict[str, Any]:
    qa, qb = _num(brk.get("quantity_a")), _num(brk.get("quantity_b"))
    amt_var = brk.get("amount_variance")
    side = brk.get("side")
    return {
        "data_layer": {
            "summary": (
                f"Side A qty {qa:g} vs Side B qty {qb:g}"
                + (f", value Δ {amt_var}" if amt_var not in (None, 0) else "")
                + (" (one-sided)" if side in ("A", "B") else "")
            ),
            "isin": brk.get("isin"),
            "side": side,
        },
        "rule_that_failed": {
            "pass": brk.get("pass_that_failed"),
            "field": field,
            "deltas": brk.get("deltas", {}),
        },
        "ai_diagnosis": {
            "primary_hypothesis": ARCHETYPE_LABELS[archetype],
            "evidence": evidence,
            "alternative": alternative,
        },
    }


def classify(brk: Dict[str, Any]) -> Dict[str, Any]:
    """Classify a break dict into the v2 taxonomy. Always returns a result."""
    side = brk.get("side")
    hint = brk.get("archetype")
    failed = brk.get("failed_rules", []) or []

    # 1) Corporate-action explained breaks (engine tags explained_category).
    if brk.get("explained_category") == "CORPORATE_ACTION":
        return _result("corporate_action_adjustment", "quantity", brk,
                       evidence=["Quantity ratio matches a corporate-action split ratio."])

    # 2) Engine structural hints.
    if hint == "duplicate_entry":
        return _result("duplicate_entry", "reference", brk,
                       evidence=["Multiple rows share the same natural key on one side."])
    if hint == "missing_counterparty_leg" or side in ("A", "B"):
        return _result("missing_leg", "counterparty", brk,
                       evidence=["No counterpart row on the other side."],
                       alternative="Could be an in-flight settlement timing lag rather than a genuine miss.")

    # 3) Two-sided: read the failing rule.
    date_fail = _first_failed(failed, "date")
    account_fail = _first_failed(failed, "account")
    mv_fail = _first_failed(failed, "market_value") or _first_failed(failed, "amount")
    qty_fail = _first_failed(failed, "quantity")

    if date_fail:
        delta = date_fail.get("delta")
        return _result("settlement_date_drift", "settlement_date", brk,
                       evidence=[f"Settlement date differs by {delta} business day(s)."])
    if account_fail:
        return _result("account_misbooking", "account_id", brk,
                       evidence=[f"Booked to {account_fail.get('value_b')} not {account_fail.get('value_a')}."])
    if mv_fail:
        delta = abs(_num(mv_fail.get("delta")))
        if delta > _MV_DISPUTE_THRESHOLD:
            return _result("emir_amount_dispute", "computed_market_value", brk,
                           evidence=[f"Market-value discrepancy of {delta:g} — a pricing/valuation dispute."],
                           alternative="Confirm the price source used on each side.")
        return _result("fx_price_rounding", "computed_market_value", brk,
                       evidence=[f"Sub-threshold value difference of {delta:g} — FX/price rounding."])
    if qty_fail:
        delta = abs(_num(qty_fail.get("delta")))
        if delta <= _QTY_ROUNDING_THRESHOLD:
            return _result("quantity_rounding", "quantity", brk,
                           evidence=[f"Quantity differs by {delta:g} — a rounding/truncation artefact."])
        return _result("nm_subset_group", "quantity", brk, confidence=0.5,
                       evidence=[f"Quantity differs by {delta:g} — possible split/subset settlement."],
                       alternative="May resolve as a many-to-one aggregate once all legs settle.")

    # 4) Fallback: genuinely ambiguous — low confidence so the SME refuses.
    if _num(brk.get("amount_variance")):
        return _result("fx_price_rounding", "computed_market_value", brk, confidence=0.4)
    if _num(brk.get("quantity_variance")):
        return _result("quantity_rounding", "quantity", brk, confidence=0.4)
    return _result("missing_leg", "unknown", brk, confidence=0.30,
                   evidence=["No decisive failing rule — insufficient signal to classify."])
