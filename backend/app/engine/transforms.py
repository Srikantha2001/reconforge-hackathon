"""Pure transform functions applied to a DataFrame column before matching."""
from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd

_OPS = {
    "abs": lambda s: pd.to_numeric(s, errors="coerce").abs(),
    "upper": lambda s: s.astype(str).str.upper(),
    "lower": lambda s: s.astype(str).str.lower(),
    "strip": lambda s: s.astype(str).str.strip(),
    "round2": lambda s: pd.to_numeric(s, errors="coerce").round(2),
}


def apply_transforms(
    df_a: pd.DataFrame, df_b: pd.DataFrame, transforms: List[Dict[str, Any]]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Apply the config's transform list to copies of both frames.

    `side` selects which frame(s) a transform applies to (default "both").
    A transform is silently skipped for a side whose frame lacks that column
    — this keeps the engine tolerant of source_a/source_b having different
    schemas, which is the normal case in reconciliation.
    """
    a = df_a.copy()
    b = df_b.copy()

    for t in transforms:
        field = t["field"]
        op = t["op"]
        side = t.get("side", "both")
        fn = _OPS[op]

        if side in ("a", "both") and field in a.columns:
            a[field] = fn(a[field])
        if side in ("b", "both") and field in b.columns:
            b[field] = fn(b[field])

    return a, b
