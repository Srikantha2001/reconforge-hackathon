"""Canonical output hash — the reproducibility contract (§2 law 4).

Same input -> identical output hash, every run. To guarantee that:
  - only match-relevant fields are hashed (no timestamps, no DB ids)
  - matched pairs and breaks are each sorted by a stable key before hashing
  - JSON is serialized with sorted keys and no incidental whitespace
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List


def canonical_output_hash(matched: List[Dict[str, Any]], breaks: List[Dict[str, Any]]) -> str:
    matched_sorted = sorted(matched, key=lambda m: m["key"])
    breaks_sorted = sorted(breaks, key=lambda b: b["break_key"])

    payload = {
        "matched": [
            {"key": m["key"], "row_a": m["row_a"], "row_b": m["row_b"]} for m in matched_sorted
        ],
        "breaks": [
            {
                "break_key": b["break_key"],
                "side": b["side"],
                "row_a": b.get("row_a"),
                "row_b": b.get("row_b"),
                "failed_rules": [
                    {"rule": r["rule"], "delta": r["delta"]}
                    for r in b.get("rule_results", [])
                    if not r["passed"]
                ],
            }
            for b in breaks_sorted
        ],
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
