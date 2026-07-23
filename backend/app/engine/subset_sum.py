"""N-to-M subset-sum matcher (P3) for the final waterfall pass.

Finds groups of side-A rows and side-B rows whose values sum to within a
tolerance, greedily (first match wins, matched rows leave the pool). Bounded by
group-size, partition-size and wall-clock guards so it can never blow up on a
large partition — it logs and skips instead.
"""
from __future__ import annotations

import itertools
import logging
import time
from typing import Any, Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)


class SubsetSumMatcher:
    def __init__(
        self,
        max_group_size_a: int = 4,
        max_group_size_b: int = 4,
        max_rows_per_partition: int = 50,
        timeout_seconds: int = 30,
    ):
        self.max_group_size_a = max_group_size_a
        self.max_group_size_b = max_group_size_b
        self.max_rows_per_partition = max_rows_per_partition
        self.timeout_seconds = timeout_seconds

    def find_matches(
        self,
        a_df: pd.DataFrame,
        b_df: pd.DataFrame,
        value_field_a: str,
        value_field_b: str,
        tolerance: float = 1.0,
        partition_col: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return match records: {row_ids_a, row_ids_b, sum_a, sum_b, variance}."""
        if partition_col and partition_col in a_df.columns and partition_col in b_df.columns:
            parts = sorted(set(a_df[partition_col]) & set(b_df[partition_col]), key=str)
            results: List[Dict[str, Any]] = []
            for key in parts:
                results.extend(
                    self._match_partition(
                        a_df[a_df[partition_col] == key],
                        b_df[b_df[partition_col] == key],
                        value_field_a,
                        value_field_b,
                        tolerance,
                    )
                )
            return results
        return self._match_partition(a_df, b_df, value_field_a, value_field_b, tolerance)

    def _match_partition(
        self,
        a_df: pd.DataFrame,
        b_df: pd.DataFrame,
        value_field_a: str,
        value_field_b: str,
        tolerance: float,
    ) -> List[Dict[str, Any]]:
        if len(a_df) + len(b_df) > self.max_rows_per_partition:
            logger.warning(
                "subset_sum: partition of %d+%d rows exceeds guard %d — skipping",
                len(a_df), len(b_df), self.max_rows_per_partition,
            )
            return []

        a_ids = list(a_df["row_id"])
        b_ids = list(b_df["row_id"])
        a_vals = {r["row_id"]: _num(r.get(value_field_a)) for _, r in a_df.iterrows()}
        b_vals = {r["row_id"]: _num(r.get(value_field_b)) for _, r in b_df.iterrows()}

        used_a: set = set()
        used_b: set = set()
        matches: List[Dict[str, Any]] = []
        start = time.time()

        for size_a in range(1, self.max_group_size_a + 1):
            for combo_a in itertools.combinations(a_ids, size_a):
                if time.time() - start > self.timeout_seconds:
                    logger.warning("subset_sum: timeout after %ss — returning partial", self.timeout_seconds)
                    return matches
                if used_a & set(combo_a):
                    continue
                sum_a = sum(a_vals[i] for i in combo_a)
                found = False
                for size_b in range(1, self.max_group_size_b + 1):
                    for combo_b in itertools.combinations(b_ids, size_b):
                        if used_b & set(combo_b):
                            continue
                        sum_b = sum(b_vals[i] for i in combo_b)
                        if abs(sum_a - sum_b) <= tolerance:
                            matches.append(
                                {
                                    "row_ids_a": list(combo_a),
                                    "row_ids_b": list(combo_b),
                                    "sum_a": sum_a,
                                    "sum_b": sum_b,
                                    "variance": abs(sum_a - sum_b),
                                }
                            )
                            used_a.update(combo_a)
                            used_b.update(combo_b)
                            found = True
                            break
                    if found:
                        break
        return matches


def _num(value: Any) -> float:
    try:
        v = float(value)
        return 0.0 if v != v else v  # NaN guard
    except (TypeError, ValueError):
        return 0.0
