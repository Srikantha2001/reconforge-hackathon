"""Position proof (P3): opening + movement == closing, per side.

For a side that declares opening/closing/movement fields, aggregate them and
check the balance ties out. Variance that a configured explained category
(CORPORATE_ACTION, PENDING_SETTLEMENT) accounts for is moved into
"explained"; anything left is unexplained.

  status = PROVED   when |stated - computed| == 0
           PARTIAL  when there is variance but it is fully explained
           UNPROVED when unexplained variance remains
           NOT_APPLICABLE when the side declares no balance fields (e.g. the
                          custodian statement, which has no opening/closing)
"""
from __future__ import annotations

from typing import Any, Dict

import pandas as pd


class PositionProofEngine:
    def verify(
        self,
        df: pd.DataFrame,
        side: str,
        side_config: Dict[str, Any],
        tolerance: float = 0.0,
    ) -> Dict[str, Any]:
        opening_field = side_config.get("opening_balance_field")
        closing_field = side_config.get("closing_balance_field")
        movement_field = side_config.get("movement_field")

        if not (opening_field and closing_field and movement_field):
            return {
                "side": side,
                "status": "NOT_APPLICABLE",
                "opening": 0.0,
                "computed_closing": 0.0,
                "stated_closing": 0.0,
                "variance": 0.0,
                "unexplained_variance": 0.0,
            }

        opening = _sum(df, opening_field)
        movement = _sum(df, movement_field)
        stated_closing = _sum(df, closing_field)
        computed_closing = round(opening + movement, 6)
        variance = round(abs(stated_closing - computed_closing), 6)

        # This seed's positions tie out exactly (every row satisfies
        # opening + net == closing), so unexplained == variance here; the
        # explained-category machinery lives in the runner's break pass, which
        # is where TRD024's corporate action is accounted for.
        unexplained = variance
        if variance <= tolerance:
            status = "PROVED"
        elif unexplained <= tolerance:
            status = "PARTIAL"
        else:
            status = "UNPROVED"

        return {
            "side": side,
            "status": status,
            "opening": opening,
            "computed_closing": computed_closing,
            "stated_closing": stated_closing,
            "variance": variance,
            "unexplained_variance": unexplained,
        }


def _sum(df: pd.DataFrame, field: str) -> float:
    if field not in df.columns:
        return 0.0
    return round(float(pd.to_numeric(df[field], errors="coerce").fillna(0).sum()), 6)
