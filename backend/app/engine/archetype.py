"""Deterministic break-archetype classifier — the no-LLM fallback for the SME
agent (§7: "Detection can be done deterministically from deltas").

This is pure heuristics over rule results and row shape. It never calls an
LLM; the SME agent (app/llm) calls into this when the provider is `stub` or
as a sanity cross-check when it isn't.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

ARCHETYPES = [
    "value_date_mismatch",
    "fx_rounding_diff",
    "partial_fill",
    "duplicate_entry",
    "fee_charge_diff",
    "timing_settlement_lag",
    "wrong_account_reference",
    "missing_counterparty_leg",
    "amount_outside_tolerance",
    "reference_format_mismatch",
]

ARCHETYPE_LABELS = {
    "value_date_mismatch": "Value-date mismatch",
    "fx_rounding_diff": "FX rounding / conversion diff",
    "partial_fill": "Partial fill / quantity mismatch",
    "duplicate_entry": "Duplicate entry",
    "fee_charge_diff": "Fee / charge difference",
    "timing_settlement_lag": "Timing / settlement lag (one-sided)",
    "wrong_account_reference": "Wrong account / reference",
    "missing_counterparty_leg": "Missing counterparty leg",
    "amount_outside_tolerance": "Amount outside tolerance",
    "reference_format_mismatch": "Reference / ID format mismatch",
}

_NICE_FRACTIONS = (0.5, 1 / 3, 2 / 3, 0.25, 0.75, 0.2, 0.4, 0.6, 0.8)


def _find_rule(rule_results: List[Dict[str, Any]], rule_type: str) -> Optional[Dict[str, Any]]:
    for r in rule_results:
        if r["type"] == rule_type and not r["passed"]:
            return r
    return None


def _find_field_containing(
    rule_results: List[Dict[str, Any]], needle: str
) -> Optional[Dict[str, Any]]:
    for r in rule_results:
        if not r["passed"] and (needle in r["field_a"].lower() or needle in r["field_b"].lower()):
            return r
    return None


def classify(
    *,
    side: str,  # "two_sided" | "one_sided_a" | "one_sided_b" | "duplicate" | "fuzzy_key_mismatch"
    rule_results: List[Dict[str, Any]],
    row_a: Optional[Dict[str, Any]] = None,
    row_b: Optional[Dict[str, Any]] = None,
    reference_date: Optional[date] = None,
    row_date: Optional[date] = None,
) -> Dict[str, Any]:
    """Return {archetype, label, explanation, confidence} from deltas alone."""

    if side == "fuzzy_key_mismatch":
        return _result(
            "reference_format_mismatch",
            "The reference/ID on each side matches once punctuation and case are "
            "normalized — same transaction, differently formatted identifier.",
            0.65,
        )

    if side == "duplicate":
        return _result(
            "duplicate_entry",
            "Multiple rows share the same reconciliation key on one side; one was "
            "paired, the rest look like duplicate postings.",
            0.8,
        )

    if side in ("one_sided_a", "one_sided_b"):
        # Recency heuristic: if this row's value_date is within the last 2 days
        # of the dataset's reference date, treat it as a timing/settlement lag
        # (the other leg likely posts next cycle) rather than a permanently
        # missing counterparty leg.
        if reference_date is not None and row_date is not None:
            age_days = (reference_date - row_date).days
            if 0 <= age_days <= 2:
                return _result(
                    "timing_settlement_lag",
                    f"This entry is only {age_days} day(s) old relative to the run date "
                    "and has no counterpart yet — looks like a settlement-cycle timing "
                    "lag rather than a genuine break.",
                    0.65,
                )
        return _result(
            "missing_counterparty_leg",
            "No corresponding row exists for this key on the other side, and it isn't "
            "recent enough to be an in-flight timing lag — the counterparty leg "
            "appears to be genuinely missing.",
            0.6,
        )

    # two_sided: a key-matched pair that failed one or more validation rules.
    date_fail = _find_rule(rule_results, "date_tolerance")
    amount_fail = _find_rule(rule_results, "numeric_tolerance")
    account_fail = _find_field_containing(rule_results, "account")
    exact_fail = _find_rule(rule_results, "exact")

    if date_fail and not amount_fail:
        delta_days = date_fail.get("delta") or 0
        return _result(
            "value_date_mismatch",
            f"Value dates differ by {delta_days} day(s), outside the configured "
            "tolerance, but every other field lines up.",
            0.8,
        )

    if amount_fail and not date_fail:
        va, vb = amount_fail.get("value_a"), amount_fail.get("value_b")
        delta = amount_fail.get("delta") or 0
        ratio = None
        try:
            fa, fb = float(va), float(vb)
            if fa and fb:
                ratio = min(fa, fb) / max(fa, fb)
        except (TypeError, ValueError):
            ratio = None

        if ratio is not None and any(abs(ratio - frac) < 0.03 for frac in _NICE_FRACTIONS):
            return _result(
                "partial_fill",
                f"One side's amount is about {round(ratio, 2)}x the other — looks like "
                "a partial fill or split settlement rather than a plain mismatch.",
                0.6,
            )
        if 0 < delta <= 0.05:
            return _result(
                "fx_rounding_diff",
                f"A sub-cent/rounding-scale difference ({delta}) consistent with an FX "
                "conversion or rounding artifact.",
                0.55,
            )
        if 0 < delta <= 5:
            return _result(
                "fee_charge_diff",
                f"Amounts differ by a small fixed-looking value ({delta}); consistent "
                "with an unaccounted fee or charge.",
                0.6,
            )
        return _result(
            "amount_outside_tolerance",
            f"Amounts differ by {delta}, exceeding the configured numeric tolerance.",
            0.7,
        )

    if account_fail:
        return _result(
            "wrong_account_reference",
            f"'{account_fail['field_a']}' does not match exactly between sides — the "
            "transaction may have posted to the wrong account.",
            0.6,
        )

    if exact_fail:
        return _result(
            "wrong_account_reference",
            f"'{exact_fail['field_a']}' does not match exactly between sides even "
            "though the reconciliation key does.",
            0.5,
        )

    if amount_fail and date_fail:
        return _result(
            "partial_fill",
            "Both amount and date disagree — consistent with a partial fill or split "
            "settlement rather than a single simple difference.",
            0.45,
        )

    return _result(
        "amount_outside_tolerance",
        "One or more validation rules failed; no more specific pattern detected from "
        "the available deltas.",
        0.3,
    )


def _result(archetype: str, explanation: str, confidence: float) -> Dict[str, Any]:
    return {
        "archetype": archetype,
        "label": ARCHETYPE_LABELS[archetype],
        "explanation": explanation,
        "confidence": confidence,
    }
