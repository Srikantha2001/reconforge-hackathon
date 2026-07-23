"""Deterministic hashing for reproducibility (P3, Law 4).

The output hash is a SHA-256 over a canonical, sorted, timestamp-free
serialization of the matches. Amounts are formatted ``f"{v:.2f}"`` and
quantities ``f"{v:.6f}"`` before hashing (Laws 3/4) so floating-point noise
can never change the hash. Sorting the per-match strings makes the hash
independent of pass/row iteration order — same input, same hash, always.
"""
from __future__ import annotations

import hashlib
from typing import Any, Dict, List

import pandas as pd


def _fmt_amount(value: Any) -> str:
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "0.00"


def _fmt_quantity(value: Any) -> str:
    try:
        return f"{float(value):.6f}"
    except (TypeError, ValueError):
        return "0.000000"


def assign_row_ids(df: pd.DataFrame) -> pd.DataFrame:
    """Add a stable ``row_id`` column = SHA-256 of the row's pipe-joined cells.

    Identical rows get disambiguated with a ``_1``, ``_2`` … suffix so every
    row_id in the frame is unique (needed to track matched rows individually).
    """
    df = df.copy()
    seen: Dict[str, int] = {}
    ids: List[str] = []
    for _, row in df.iterrows():
        payload = "|".join(str(row[c]) for c in df.columns)
        base = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
        if base in seen:
            seen[base] += 1
            ids.append(f"{base}_{seen[base]}")
        else:
            seen[base] = 0
            ids.append(base)
    df["row_id"] = ids
    return df


def canonicalize_matches(matches: List[Dict[str, Any]]) -> str:
    """Sorted, newline-joined canonical string over all match records."""
    lines: List[str] = []
    for m in matches:
        lines.append(
            "|".join(
                [
                    str(m.get("pass_number", "")),
                    str(m.get("isin", "") or ""),
                    str(m.get("match_type", "")),
                    _fmt_quantity(m.get("quantity_a", 0)),
                    _fmt_quantity(m.get("quantity_b", 0)),
                    _fmt_amount(m.get("amount_a", 0)),
                    _fmt_amount(m.get("amount_b", 0)),
                    _fmt_quantity(m.get("quantity_variance", 0)),
                    _fmt_amount(m.get("amount_variance", 0)),
                ]
            )
        )
    return "\n".join(sorted(lines))


def compute_hash(canonical_string: str) -> str:
    return hashlib.sha256(canonical_string.encode("utf-8")).hexdigest()


def compute_run_hash(matches: List[Dict[str, Any]]) -> str:
    return compute_hash(canonicalize_matches(matches))
