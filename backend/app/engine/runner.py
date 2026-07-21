"""The deterministic engine entry point: transforms -> key match -> rule eval.

Pure function of (df_a, df_b, config) -> ReconResult. No I/O, no LLM calls —
this module is the one thing in ReconForge that must behave identically on
every run given the same inputs (§2 law 1 and law 4).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Optional

import pandas as pd

from . import archetype as archetype_mod
from .hashing import canonical_output_hash
from .matching import _to_date, build_key, evaluate_pair, score_pair
from .transforms import apply_transforms

_ALNUM_RE = re.compile(r"[^A-Za-z0-9]")


@dataclass
class ReconResult:
    matched: List[Dict[str, Any]]
    breaks: List[Dict[str, Any]]
    total_a: int
    total_b: int
    matched_count: int
    break_count: int
    match_rate: float
    output_hash: str


def _severity(side: str, archetype: str, rule_results: List[Dict[str, Any]]) -> str:
    """Deterministic severity bands (locked default, §J1)."""
    if archetype == "missing_counterparty_leg":
        return "high"
    if side == "fuzzy_key_mismatch":
        return "medium"
    if side in ("one_sided_a", "one_sided_b"):
        return "medium" if archetype == "timing_settlement_lag" else "high"
    for r in rule_results:
        if r["type"] == "numeric_tolerance" and not r["passed"]:
            delta = r.get("delta") or 0
            return "high" if delta > 100 else "medium"
    for r in rule_results:
        if r["type"] == "date_tolerance" and not r["passed"]:
            delta = r.get("delta") or 0
            return "medium" if delta >= 3 else "low"
    return "medium"


def _normalize_key(value: str) -> str:
    return _ALNUM_RE.sub("", value).upper()


def _date_field_names(rules: List[Dict[str, Any]]) -> Optional[tuple[str, str]]:
    for r in rules:
        if r["type"] == "date_tolerance":
            return r["field_a"], r["field_b"]
    return None


def _make_break(
    *,
    break_key: str,
    side: str,
    row_a: Optional[Dict[str, Any]],
    row_b: Optional[Dict[str, Any]],
    rule_results: Optional[List[Dict[str, Any]]] = None,
    reference_date: Optional[date] = None,
    row_date: Optional[date] = None,
) -> Dict[str, Any]:
    rule_results = rule_results or []
    cls = archetype_mod.classify(
        side=side,
        rule_results=rule_results,
        row_a=row_a,
        row_b=row_b,
        reference_date=reference_date,
        row_date=row_date,
    )
    deltas = {r["rule"]: r["delta"] for r in rule_results if not r["passed"]}
    sev = _severity(side, cls["archetype"], rule_results)
    return {
        "break_key": break_key,
        "side": side,
        "row_a": row_a,
        "row_b": row_b,
        "rule_results": rule_results,
        "failed_rules": [r["rule"] for r in rule_results if not r["passed"]],
        "deltas": deltas,
        "archetype": cls["archetype"],
        "archetype_label": cls["label"],
        "explanation": cls["explanation"],
        "sme_confidence": cls["confidence"],
        "severity": sev,
    }


def _merge_fuzzy_key_breaks(
    breaks: List[Dict[str, Any]],
    key_cols_a: List[str],
    key_cols_b: List[str],
    rules: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Advisory-only enrichment pass (§7 archetype #10): if a one-sided-A break's
    key matches a one-sided-B break's key once punctuation/case is stripped,
    re-label the pair as a reference/ID format mismatch instead of two separate
    "missing leg" breaks. This never changes match_rate — both rows stay breaks,
    just explained better. Simple one-to-one greedy pairing, deterministic
    because both input lists are already in stable (sorted-key) order.
    """
    one_a = [b for b in breaks if b["side"] == "one_sided_a"]
    one_b = [b for b in breaks if b["side"] == "one_sided_b"]
    if not one_a or not one_b:
        return breaks

    used_b_idx: set[int] = set()
    merged: List[Dict[str, Any]] = []
    consumed_a_ids = set()
    consumed_b_ids = set()

    for ba in one_a:
        key_a_norm = _normalize_key(build_key(ba["row_a"], key_cols_a))
        if not key_a_norm:
            continue
        for j, bb in enumerate(one_b):
            if j in used_b_idx:
                continue
            key_b_norm = _normalize_key(build_key(bb["row_b"], key_cols_b))
            if key_b_norm and key_b_norm == key_a_norm:
                used_b_idx.add(j)
                _, rule_results = evaluate_pair(rules, ba["row_a"], bb["row_b"])
                merged.append(
                    _make_break(
                        break_key=f"fuzzy::{ba['break_key']}::{bb['break_key']}",
                        side="fuzzy_key_mismatch",
                        row_a=ba["row_a"],
                        row_b=bb["row_b"],
                        rule_results=rule_results,
                    )
                )
                consumed_a_ids.add(id(ba))
                consumed_b_ids.add(id(bb))
                break

    if not merged:
        return breaks

    remaining = [
        b for b in breaks if id(b) not in consumed_a_ids and id(b) not in consumed_b_ids
    ]
    return remaining + merged


def reconcile(df_a: pd.DataFrame, df_b: pd.DataFrame, config: Dict[str, Any]) -> ReconResult:
    key_cols_a = config["source_a"]["key_columns"]
    key_cols_b = config["source_b"]["key_columns"]
    rules = config["match_rules"]
    transforms = config.get("transforms", [])

    ta, tb = apply_transforms(df_a, df_b, transforms)

    rows_a = ta.to_dict(orient="records")
    rows_b = tb.to_dict(orient="records")

    date_fields = _date_field_names(rules)
    reference_date: Optional[date] = None
    if date_fields:
        fa, fb = date_fields
        all_dates = [
            d
            for d in (
                [_to_date(r.get(fa)) for r in rows_a] + [_to_date(r.get(fb)) for r in rows_b]
            )
            if d is not None
        ]
        if all_dates:
            reference_date = max(all_dates)

    def _row_date(row: Optional[Dict[str, Any]], field: Optional[str]) -> Optional[date]:
        if row is None or field is None:
            return None
        return _to_date(row.get(field))

    groups_a: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows_a:
        groups_a.setdefault(build_key(row, key_cols_a), []).append(row)

    groups_b: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows_b:
        groups_b.setdefault(build_key(row, key_cols_b), []).append(row)

    matched: List[Dict[str, Any]] = []
    breaks: List[Dict[str, Any]] = []

    all_keys = sorted(set(groups_a) | set(groups_b))

    for key in all_keys:
        a_rows = groups_a.get(key, [])
        b_rows = groups_b.get(key, [])

        if a_rows and not b_rows:
            for i, ra in enumerate(a_rows):
                bkey = f"{key}#a{i}" if len(a_rows) > 1 else key
                breaks.append(
                    _make_break(
                        break_key=bkey,
                        side="one_sided_a",
                        row_a=ra,
                        row_b=None,
                        reference_date=reference_date,
                        row_date=_row_date(ra, date_fields[0] if date_fields else None),
                    )
                )
            continue

        if b_rows and not a_rows:
            for i, rb in enumerate(b_rows):
                bkey = f"{key}#b{i}" if len(b_rows) > 1 else key
                breaks.append(
                    _make_break(
                        break_key=bkey,
                        side="one_sided_b",
                        row_a=None,
                        row_b=rb,
                        reference_date=reference_date,
                        row_date=_row_date(rb, date_fields[1] if date_fields else None),
                    )
                )
            continue

        # Both sides have the key: one-to-one only (§E2). Greedy best-pair
        # assignment when either side has more than one row under the key.
        remaining_a = list(enumerate(a_rows))
        remaining_b = list(enumerate(b_rows))
        pairs: List[tuple[int, int, List[Dict[str, Any]], float]] = []

        for ia, ra in remaining_a:
            for ib, rb in remaining_b:
                _, rule_results = evaluate_pair(rules, ra, rb)
                pairs.append((ia, ib, rule_results, score_pair(rule_results)))

        pairs.sort(key=lambda p: p[3], reverse=True)
        used_a: set[int] = set()
        used_b: set[int] = set()
        suffix = 0
        for ia, ib, rule_results, _score in pairs:
            if ia in used_a or ib in used_b:
                continue
            used_a.add(ia)
            used_b.add(ib)
            ra, rb = a_rows[ia], b_rows[ib]
            matched_ok = all(r["passed"] for r in rule_results)
            pair_key = key if (len(a_rows) == 1 and len(b_rows) == 1) else f"{key}#{suffix}"
            suffix += 1
            if matched_ok:
                matched.append({"key": pair_key, "row_a": ra, "row_b": rb})
            else:
                breaks.append(
                    _make_break(
                        break_key=pair_key, side="two_sided", row_a=ra, row_b=rb,
                        rule_results=rule_results,
                    )
                )

        # Leftover rows under a shared key that couldn't be one-to-one paired
        # (duplicates / extra legs).
        for ia, ra in remaining_a:
            if ia not in used_a:
                breaks.append(
                    _make_break(break_key=f"{key}#dupA{ia}", side="duplicate", row_a=ra, row_b=None)
                )
        for ib, rb in remaining_b:
            if ib not in used_b:
                breaks.append(
                    _make_break(break_key=f"{key}#dupB{ib}", side="duplicate", row_a=None, row_b=rb)
                )

    breaks = _merge_fuzzy_key_breaks(breaks, key_cols_a, key_cols_b, rules)

    total_a, total_b = len(rows_a), len(rows_b)
    matched_count, break_count = len(matched), len(breaks)
    denom = max(total_a, total_b) or 1
    match_rate = round(matched_count / denom, 6)
    output_hash = canonical_output_hash(matched, breaks)

    return ReconResult(
        matched=matched,
        breaks=breaks,
        total_a=total_a,
        total_b=total_b,
        matched_count=matched_count,
        break_count=break_count,
        match_rate=match_rate,
        output_hash=output_hash,
    )
