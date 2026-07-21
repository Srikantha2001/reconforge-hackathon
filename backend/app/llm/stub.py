"""Deterministic, no-API-key provider.

This is the default (`LLM_PROVIDER=stub`) so the whole app — including NL
authoring — runs fully offline. It also doubles as the fallback every real
provider degrades to on error (fallback ladder rung #3), and it is what makes
the reproducibility test meaningful for anything that touches an "LLM" step
in CI.

`author_config` does lightweight keyword/regex extraction over the NL text
and the uploaded CSV headers; if it can't confidently ground a rule in the
actual headers, it falls back to the pre-approved seeded config rather than
guessing.
"""
from __future__ import annotations

import copy
import re
from typing import Any, Dict, List, Optional

from .base import LLMProvider

_KEY_CANDIDATES = ("trade_id", "id", "ref", "reference", "transaction_id", "txn_id")
_AMOUNT_CANDIDATES = ("amount", "amt", "value")
_CCY_CANDIDATES = ("ccy", "currency")
_DATE_CANDIDATES = ("value_date", "date", "trade_date", "settlement_date", "posting_date")
_ACCOUNT_CANDIDATES = ("account", "acct")

_RESOLUTION_TEMPLATES = {
    "value_date_mismatch": "Confirm the correct value date with the counterparty; if this "
    "pattern recurs, consider widening the date tolerance via Loop A.",
    "fx_rounding_diff": "Accept as an FX rounding artifact if within house tolerance for the "
    "currency pair; otherwise confirm the conversion rate used.",
    "partial_fill": "Verify whether this is a genuine split settlement; if so, link the legs "
    "manually so future occurrences short-circuit via resolution memory.",
    "duplicate_entry": "Investigate the duplicate posting with the source system and reverse "
    "or write off the extra entry once confirmed.",
    "fee_charge_diff": "Check the fee schedule for this account/counterparty; post an "
    "adjusting entry for the charge if legitimate.",
    "timing_settlement_lag": "No action needed yet — allow the next settlement cycle to post "
    "the counterpart leg before escalating.",
    "wrong_account_reference": "Contact the posting team to confirm the correct account and "
    "arrange a reclassification.",
    "missing_counterparty_leg": "Chase the counterparty for the missing leg; escalate if it "
    "remains unposted beyond the next cycle.",
    "amount_outside_tolerance": "Investigate the amount discrepancy with the source system; "
    "do not auto-resolve without a documented reason.",
    "reference_format_mismatch": "Treat as the same transaction; consider normalizing "
    "reference formats at source to prevent recurrence.",
}

_RULE_DESCRIPTIONS = {
    "exact": "must match exactly",
    "numeric_tolerance": "must match within a tolerance of {tolerance}",
    "date_tolerance": "must match within {tolerance_days} day(s)",
}

_TRANSFORM_DESCRIPTIONS = {
    "abs": "takes the absolute value of",
    "upper": "upper-cases",
    "lower": "lower-cases",
    "strip": "strips whitespace from",
    "round2": "rounds to 2 decimal places",
}


def _find_column(columns: List[str], candidates: tuple) -> Optional[str]:
    lower = {c.lower(): c for c in columns}
    for cand in candidates:
        if cand in lower:
            return lower[cand]
    return None


def _extract_float(text: str, keywords: tuple) -> Optional[float]:
    for kw in keywords:
        m = re.search(rf"{kw}[^0-9]{{0,15}}([0-9]+\.?[0-9]*)", text, re.IGNORECASE)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                continue
    return None


def _extract_int_days(text: str) -> Optional[int]:
    m = re.search(r"([0-9]+)\s*day", text, re.IGNORECASE)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return None
    return None


class StubProvider(LLMProvider):
    name = "stub"

    def author_config(
        self, nl_description: str, columns_a: List[str], columns_b: List[str]
    ) -> Dict[str, Any]:
        key_a = _find_column(columns_a, _KEY_CANDIDATES)
        key_b = _find_column(columns_b, _KEY_CANDIDATES)

        if not key_a or not key_b:
            # Can't ground a join key in the actual headers — refuse to guess.
            # Fall back to the pre-approved seeded config (fallback ladder #3).
            from ..seed.generator import DEFAULT_CONFIG

            return copy.deepcopy(DEFAULT_CONFIG)

        amount_a = _find_column(columns_a, _AMOUNT_CANDIDATES)
        amount_b = _find_column(columns_b, _AMOUNT_CANDIDATES)
        ccy_a = _find_column(columns_a, _CCY_CANDIDATES)
        ccy_b = _find_column(columns_b, _CCY_CANDIDATES)
        date_a = _find_column(columns_a, _DATE_CANDIDATES)
        date_b = _find_column(columns_b, _DATE_CANDIDATES)
        account_a = _find_column(columns_a, _ACCOUNT_CANDIDATES)
        account_b = _find_column(columns_b, _ACCOUNT_CANDIDATES)

        amount_tolerance = _extract_float(nl_description, ("toleranc", "within", "cent")) or 0.01
        date_tolerance_days = _extract_int_days(nl_description)
        if date_tolerance_days is None:
            date_tolerance_days = 2

        name_match = re.search(r"[\"“]([^\"”]+)[\"”]", nl_description)
        recon_name = name_match.group(1).replace(" ", "_") if name_match else "NL_Authored_Recon"

        transforms: List[Dict[str, Any]] = []
        if amount_a and amount_b:
            transforms.append({"field": amount_a, "op": "abs"})
        if ccy_a and ccy_b:
            transforms.append({"field": ccy_a, "op": "upper"})

        match_rules: List[Dict[str, Any]] = [
            {"field_a": key_a, "field_b": key_b, "type": "exact"}
        ]
        if amount_a and amount_b:
            match_rules.append(
                {
                    "field_a": amount_a,
                    "field_b": amount_b,
                    "type": "numeric_tolerance",
                    "tolerance": amount_tolerance,
                }
            )
        if date_a and date_b:
            match_rules.append(
                {
                    "field_a": date_a,
                    "field_b": date_b,
                    "type": "date_tolerance",
                    "tolerance_days": date_tolerance_days,
                }
            )
        if account_a and account_b and "account" in nl_description.lower():
            match_rules.append({"field_a": account_a, "field_b": account_b, "type": "exact"})

        return {
            "recon_name": recon_name,
            "source_a": {"alias": "source_a", "key_columns": [key_a]},
            "source_b": {"alias": "source_b", "key_columns": [key_b]},
            "transforms": transforms,
            "match_rules": match_rules,
        }

    def summarize_config(self, config: Dict[str, Any]) -> str:
        a, b = config["source_a"], config["source_b"]
        lines = [
            f"'{config['recon_name']}' matches '{a['alias']}' rows to '{b['alias']}' rows by "
            f"joining {', '.join(a['key_columns'])} to {', '.join(b['key_columns'])} exactly."
        ]
        transforms = config.get("transforms", [])
        if transforms:
            parts = [f"{_TRANSFORM_DESCRIPTIONS.get(t['op'], t['op'])} {t['field']}" for t in transforms]
            lines.append("Before matching, it " + "; ".join(parts) + ".")
        rule_lines = []
        for r in config["match_rules"]:
            desc = _RULE_DESCRIPTIONS.get(r["type"], r["type"]).format(**r)
            rule_lines.append(f"{r['field_a']} (vs {r['field_b']}) {desc}")
        lines.append("For a pair to be considered matched, every one of these must hold: " + "; ".join(rule_lines) + ".")
        return " ".join(lines)

    def sme_explain(
        self, break_row: Dict[str, Any], base_archetype: Dict[str, Any]
    ) -> Dict[str, Any]:
        archetype = base_archetype["archetype"]
        return {
            "archetype": archetype,
            "label": base_archetype["label"],
            "explanation": base_archetype["explanation"],
            "suggested_resolution": _RESOLUTION_TEMPLATES.get(
                archetype, "Route to a human reviewer — no confident pattern detected."
            ),
            "confidence": base_archetype["confidence"],
        }

    def judge_evaluate(
        self, sme_result: Dict[str, Any], break_row: Dict[str, Any], threshold: float
    ) -> Dict[str, Any]:
        confidence = sme_result["confidence"]
        decision = "accept" if confidence >= threshold else "route_to_human"
        reason = (
            f"SME confidence {confidence:.2f} "
            + (f">= threshold {threshold:.2f} — auto-accepting." if decision == "accept"
               else f"< threshold {threshold:.2f} — routing to a human reviewer.")
        )
        return {"decision": decision, "confidence": confidence, "reason": reason}

    def draft_chaser(self, break_row: Dict[str, Any]) -> Dict[str, Any]:
        row_a, row_b = break_row.get("row_a") or {}, break_row.get("row_b") or {}
        counterparty = row_a.get("counterparty") or row_b.get("description") or "the counterparty"
        key = break_row.get("break_key", "this item")
        label = break_row.get("archetype_label", "a reconciliation break")
        body = (
            f"Hello,\n\nWhile reconciling our records we found a discrepancy on {key} "
            f"({label}).\n\n{break_row.get('explanation', '')}\n\n"
            f"Could you confirm the details on your side so we can close this out?\n\n"
            f"Thanks,\nReconForge (draft — reviewed by a human before sending)"
        )
        return {
            "to": counterparty,
            "subject": f"Query regarding {key} — {label}",
            "body": body,
        }

    def propose_config_change(
        self, current_config: Dict[str, Any], aggregated_deltas: Dict[str, Any]
    ) -> Dict[str, Any]:
        proposed = copy.deepcopy(current_config)
        rule_type = aggregated_deltas.get("type")
        field_a = aggregated_deltas.get("field_a")
        field_b = aggregated_deltas.get("field_b")
        observed = aggregated_deltas.get("observed_deltas", [])
        count = aggregated_deltas.get("count", len(observed))

        if not observed:
            return {"proposed_config": proposed, "rationale": "No aggregated deltas to act on."}

        target_rule = None
        for r in proposed["match_rules"]:
            if r["field_a"] == field_a and r["field_b"] == field_b and r["type"] == rule_type:
                target_rule = r
                break
        if target_rule is None:
            return {"proposed_config": proposed, "rationale": "No matching rule found to refine."}

        if rule_type == "date_tolerance":
            new_days = int(max(observed))
            old_days = target_rule["tolerance_days"]
            target_rule["tolerance_days"] = new_days
            rationale = (
                f"{count} manually-confirmed matches showed a consistent {new_days}-day "
                f"value-date gap, beyond the current tolerance of {old_days} day(s). "
                f"Proposing to widen tolerance_days to {new_days} so these auto-match."
            )
        elif rule_type == "numeric_tolerance":
            new_tol = round(max(observed) * 1.05, 2)
            old_tol = target_rule["tolerance"]
            target_rule["tolerance"] = new_tol
            rationale = (
                f"{count} manually-confirmed matches showed amount deltas up to "
                f"{max(observed)}, beyond the current tolerance of {old_tol}. Proposing to "
                f"widen tolerance to {new_tol}."
            )
        else:
            rationale = f"No deterministic widening strategy for rule type '{rule_type}'."

        return {"proposed_config": proposed, "rationale": rationale}
