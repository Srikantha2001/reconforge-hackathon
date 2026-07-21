"""Key-building and match-rule evaluation — pure functions, no I/O."""
from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

KEY_SEP = "||"


def build_key(row: Dict[str, Any], key_columns: List[str]) -> str:
    """Composite key from one or more columns, positionally paired across
    source_a/source_b by the caller (key_columns lists are matched by index).
    """
    return KEY_SEP.join(str(row.get(col, "")) for col in key_columns)


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        if isinstance(value, str) and not value.strip():
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    s = str(value).strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s).date()
    except ValueError:
        return None


def evaluate_rule(rule: Dict[str, Any], row_a: Dict[str, Any], row_b: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluate a single match_rule against a candidate pair.

    Returns {passed, rule, value_a, value_b, delta} — delta is a JSON-safe
    scalar describing the disagreement magnitude (used for archetype
    classification and Loop A aggregation).
    """
    field_a, field_b, rtype = rule["field_a"], rule["field_b"], rule["type"]
    va, vb = row_a.get(field_a), row_b.get(field_b)

    if rtype == "exact":
        passed = str(va).strip() == str(vb).strip()
        delta = None if passed else _string_diff_delta(va, vb)
    elif rtype == "numeric_tolerance":
        fa, fb = _to_float(va), _to_float(vb)
        if fa is None or fb is None:
            passed, delta = False, None
        else:
            diff = abs(fa - fb)
            passed = diff <= rule["tolerance"] + 1e-9
            delta = round(diff, 6)
    elif rtype == "date_tolerance":
        da, db = _to_date(va), _to_date(vb)
        if da is None or db is None:
            passed, delta = False, None
        else:
            diff_days = abs((da - db).days)
            passed = diff_days <= rule["tolerance_days"]
            delta = diff_days
    else:  # pragma: no cover - schema guarantees this can't happen
        passed, delta = False, None

    return {
        "rule": f"{field_a}<->{field_b}:{rtype}",
        "field_a": field_a,
        "field_b": field_b,
        "type": rtype,
        "passed": passed,
        "value_a": _jsonable(va),
        "value_b": _jsonable(vb),
        "delta": delta,
    }


def _string_diff_delta(va: Any, vb: Any) -> Optional[float]:
    """A crude 0..1 dissimilarity score for exact-match string breaks."""
    sa, sb = str(va).strip(), str(vb).strip()
    if not sa and not sb:
        return 0.0
    longer = max(len(sa), len(sb)) or 1
    # Cheap edit-distance-free dissimilarity: fraction of differing chars
    # over the longer string (good enough to feed archetype heuristics).
    common = sum(1 for x, y in zip(sa, sb) if x == y)
    return round(1 - common / longer, 4)


def _jsonable(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def evaluate_pair(
    rules: List[Dict[str, Any]], row_a: Dict[str, Any], row_b: Dict[str, Any]
) -> Tuple[bool, List[Dict[str, Any]]]:
    """Evaluate all match_rules; matched iff every rule passes."""
    results = [evaluate_rule(rule, row_a, row_b) for rule in rules]
    matched = all(r["passed"] for r in results)
    return matched, results


def score_pair(rule_results: List[Dict[str, Any]]) -> float:
    """Higher is better: count of passing rules, tie-broken by small deltas."""
    passed = sum(1 for r in rule_results if r["passed"])
    penalty = sum((r["delta"] or 0) for r in rule_results if not r["passed"] and isinstance(r["delta"], (int, float)))
    return passed - 0.001 * penalty
