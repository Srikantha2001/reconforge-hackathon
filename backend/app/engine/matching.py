"""Matching waterfall (P3) — the deterministic core. Pure, no I/O, no LLM.

``MatchingWaterfall.execute(side_a, side_b)`` runs the config's ordered passes
over shrinking pools and returns the matches, per-pass stats, and residuals.
Value comparisons use ``Decimal`` for money/quantity precision (Law 3) and
business-day-aware date tolerance. A None/NaN value makes a rule fail — it
never raises.

Pass types: ONE_TO_ONE, ONE_TO_MANY, MANY_TO_ONE, N_TO_M_SUBSET_SUM,
CASS_SPECIFIC. An optional ``restrict_isins`` scopes a pass to specific ISINs
(others stay in the pool for later passes).
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Set, Tuple

import pandas as pd

from .business_days import business_day_diff, calendar_day_diff
from .subset_sum import SubsetSumMatcher


def _dec(value: Any) -> Optional[Decimal]:
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() in {"nan", "nat", "none"}:
        return None
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return None


class MatchingWaterfall:
    def __init__(
        self,
        config: Dict[str, Any],
        aux_data: Dict[str, pd.DataFrame] = None,
        holidays: Dict[str, Set[str]] = None,
        guards: Dict[str, int] = None,
    ):
        self.config = config
        self.aux_data = aux_data or {}
        self.holidays = holidays or {}
        self.guards = guards or {}
        self.matches: List[Dict[str, Any]] = []
        self.pass_stats: List[Dict[str, Any]] = []

    # -- public ------------------------------------------------------------
    def execute(self, side_a: pd.DataFrame, side_b: pd.DataFrame) -> Dict[str, Any]:
        total_a, total_b = len(side_a), len(side_b)
        pool_a = side_a.copy()
        pool_b = side_b.copy()

        for pass_cfg in self.config.get("matching_waterfall", []):
            restrict = pass_cfg.get("restrict_isins")
            if restrict:
                in_a = pool_a[pool_a.get("isin").isin(restrict)] if "isin" in pool_a.columns else pool_a.iloc[0:0]
                out_a = pool_a[~pool_a.get("isin").isin(restrict)] if "isin" in pool_a.columns else pool_a
                in_b = pool_b[pool_b.get("isin").isin(restrict)] if "isin" in pool_b.columns else pool_b.iloc[0:0]
                out_b = pool_b[~pool_b.get("isin").isin(restrict)] if "isin" in pool_b.columns else pool_b
            else:
                in_a, out_a = pool_a, pool_a.iloc[0:0]
                in_b, out_b = pool_b, pool_b.iloc[0:0]

            matched_a_ids, matched_b_ids = self._run_pass(pass_cfg, in_a, in_b)

            remaining_in_a = in_a[~in_a["row_id"].isin(matched_a_ids)]
            remaining_in_b = in_b[~in_b["row_id"].isin(matched_b_ids)]
            pool_a = pd.concat([out_a, remaining_in_a])
            pool_b = pd.concat([out_b, remaining_in_b])

            self.pass_stats.append(
                {
                    "pass_number": pass_cfg.get("pass"),
                    "pass_name": pass_cfg.get("name"),
                    "match_type": pass_cfg.get("type"),
                    "matched_count": len(matched_a_ids),
                    "pool_a_remaining": len(pool_a),
                    "pool_b_remaining": len(pool_b),
                }
            )

        matched_a_count = total_a - len(pool_a)
        match_rate = round(matched_a_count / total_a * 100, 2) if total_a else 0.0
        return {
            "matches": self.matches,
            "pass_stats": self.pass_stats,
            "residual_a": pool_a,
            "residual_b": pool_b,
            "match_rate_pct": match_rate,
            "total_matched": matched_a_count,
            "total_breaks": len(pool_a) + len(pool_b),
        }

    # -- dispatch ----------------------------------------------------------
    def _run_pass(self, cfg, pool_a, pool_b) -> Tuple[Set[str], Set[str]]:
        ptype = cfg.get("type")
        if ptype == "ONE_TO_ONE":
            return self._one_to_one(cfg, pool_a, pool_b)
        if ptype == "ONE_TO_MANY":
            return self._one_to_many(cfg, pool_a, pool_b)
        if ptype == "MANY_TO_ONE":
            return self._many_to_one(cfg, pool_a, pool_b)
        if ptype == "N_TO_M_SUBSET_SUM":
            return self._n_to_m(cfg, pool_a, pool_b)
        if ptype == "CASS_SPECIFIC":
            return self._cass_specific(cfg, pool_a, pool_b)
        return set(), set()

    # -- pass handlers -----------------------------------------------------
    def _one_to_one(self, cfg, pool_a, pool_b) -> Tuple[Set[str], Set[str]]:
        key_rules = cfg.get("key_rules", [])
        value_rules = cfg.get("value_rules", [])
        matched_a: Set[str] = set()
        matched_b: Set[str] = set()

        b_rows = list(pool_b.to_dict("records"))
        for a in pool_a.to_dict("records"):
            for b in b_rows:
                if b["row_id"] in matched_b:
                    continue
                if not self._keys_match(key_rules, a, b):
                    continue
                if all(self._check_value_rule(a, b, r)[0] for r in value_rules):
                    matched_a.add(a["row_id"])
                    matched_b.add(b["row_id"])
                    self._record_match(cfg, [a], [b])
                    break
        return matched_a, matched_b

    def _one_to_many(self, cfg, pool_a, pool_b) -> Tuple[Set[str], Set[str]]:
        key_rules = cfg.get("key_rules", [])
        value_rules = cfg.get("value_rules", [])
        group_by = cfg.get("group_by_b", ["isin"])
        agg_field = cfg.get("aggregate_field_b", "quantity")
        matched_a: Set[str] = set()
        matched_b: Set[str] = set()

        for a in pool_a.to_dict("records"):
            avail_b = pool_b[~pool_b["row_id"].isin(matched_b)]
            grp = avail_b[avail_b[group_by[0]].astype(str) == str(a.get(_field_a(key_rules[0])))] \
                if key_rules else avail_b
            if grp.empty:
                continue
            b_agg = dict(a)
            b_agg[agg_field] = pd.to_numeric(grp[agg_field], errors="coerce").sum()
            if all(self._check_value_rule(a, b_agg, r)[0] for r in value_rules):
                b_records = grp.to_dict("records")
                matched_a.add(a["row_id"])
                matched_b.update(r["row_id"] for r in b_records)
                self._record_match(cfg, [a], b_records)
        return matched_a, matched_b

    def _many_to_one(self, cfg, pool_a, pool_b) -> Tuple[Set[str], Set[str]]:
        key_rules = cfg.get("key_rules", [])
        value_rules = cfg.get("value_rules", [])
        group_by = cfg.get("group_by_a", ["isin"])
        agg_field = cfg.get("aggregate_field_a", "quantity")
        matched_a: Set[str] = set()
        matched_b: Set[str] = set()

        for b in pool_b.to_dict("records"):
            avail_a = pool_a[~pool_a["row_id"].isin(matched_a)]
            grp = avail_a[avail_a[group_by[0]].astype(str) == str(b.get(_field_b(key_rules[0])))] \
                if key_rules else avail_a
            if grp.empty:
                continue
            a_agg = dict(b)
            a_agg[agg_field] = pd.to_numeric(grp[agg_field], errors="coerce").sum()
            # value rules compare field_a (aggregated A) to field_b (single B).
            if all(self._check_value_rule(a_agg, b, r)[0] for r in value_rules):
                a_records = grp.to_dict("records")
                matched_b.add(b["row_id"])
                matched_a.update(r["row_id"] for r in a_records)
                self._record_match(cfg, a_records, [b])
        return matched_a, matched_b

    def _n_to_m(self, cfg, pool_a, pool_b) -> Tuple[Set[str], Set[str]]:
        guard = cfg.get("performance_guard", {})
        matcher = SubsetSumMatcher(
            max_group_size_a=guard.get("max_group_size", self.guards.get("max_group_size", 4)),
            max_group_size_b=guard.get("max_group_size", self.guards.get("max_group_size", 4)),
            max_rows_per_partition=guard.get("max_rows_per_partition", self.guards.get("max_rows_per_partition", 50)),
            timeout_seconds=guard.get("timeout_seconds", self.guards.get("timeout_seconds", 30)),
        )
        results = matcher.find_matches(
            pool_a, pool_b,
            value_field_a=cfg.get("value_field_a", "quantity"),
            value_field_b=cfg.get("value_field_b", "quantity"),
            tolerance=cfg.get("tolerance", 1.0),
            partition_col=cfg.get("partition_col"),
        )
        matched_a: Set[str] = set()
        matched_b: Set[str] = set()
        a_by_id = {r["row_id"]: r for r in pool_a.to_dict("records")}
        b_by_id = {r["row_id"]: r for r in pool_b.to_dict("records")}
        for res in results:
            a_records = [a_by_id[i] for i in res["row_ids_a"]]
            b_records = [b_by_id[i] for i in res["row_ids_b"]]
            matched_a.update(res["row_ids_a"])
            matched_b.update(res["row_ids_b"])
            self._record_match(cfg, a_records, b_records)
        return matched_a, matched_b

    def _cass_specific(self, cfg, pool_a, pool_b) -> Tuple[Set[str], Set[str]]:
        # Structurally a ONE_TO_ONE with a shortfall value rule; the seed's
        # POSITION recon does not use it (CASS is handled by its own service in
        # P6). Implemented so a CASS_SPECIFIC pass never crashes a run.
        return self._one_to_one(cfg, pool_a, pool_b)

    # -- rule evaluation ---------------------------------------------------
    def _keys_match(self, key_rules, a, b) -> bool:
        for r in key_rules:
            va, vb = a.get(r["field_a"]), b.get(r["field_b"])
            if r.get("match_type", "EXACT") == "EXACT":
                if str(va).strip() != str(vb).strip():
                    return False
            else:
                if not self._check_value_rule(a, b, r)[0]:
                    return False
        return True

    def _check_value_rule(self, a, b, rule) -> Tuple[bool, Optional[float]]:
        """Return (passed, delta). None/NaN values fail the rule, never raise."""
        mt = rule.get("match_type")
        va, vb = a.get(rule["field_a"]), b.get(rule["field_b"])

        if mt == "EXACT":
            passed = va is not None and vb is not None and str(va).strip() == str(vb).strip()
            return passed, None

        if mt == "NUMERIC_TOLERANCE":
            da, db = _dec(va), _dec(vb)
            if da is None or db is None:
                return False, None
            diff = abs(da - db)
            tol = Decimal(str(rule.get("tolerance", 0)))
            return diff <= tol, float(diff)

        if mt == "ASYMMETRIC_TOLERANCE":
            da, db = _dec(va), _dec(vb)
            if da is None or db is None:
                return False, None
            diff = da - db
            lo = Decimal(str(rule.get("min_variance", 0)))
            hi = Decimal(str(rule.get("max_variance", 0)))
            return lo <= diff <= hi, float(diff)

        if mt == "DATE_TOLERANCE":
            market = rule.get("calendar_market", "TARGET2")
            if rule.get("business_days_only", True):
                diff = business_day_diff(va, vb, self.holidays.get(market, set()))
            else:
                diff = calendar_day_diff(va, vb)
            if diff is None:
                return False, None
            return diff <= int(rule.get("tolerance_days", 0)), diff

        if mt == "CASS_SHORTFALL":
            da, db = _dec(va), _dec(vb)
            if da is None or db is None:
                return False, None
            shortfall = da - db
            return shortfall <= Decimal(str(rule.get("tolerance", 0))), float(shortfall)

        return False, None

    # -- match recording ---------------------------------------------------
    def _record_match(self, cfg, a_records: List[dict], b_records: List[dict]) -> None:
        qty_a = sum(_num(r.get("quantity")) for r in a_records)
        qty_b = sum(_num(r.get("quantity")) for r in b_records)
        amt_a = sum(_num(r.get("computed_market_value", r.get("market_value"))) for r in a_records)
        amt_b = sum(_num(r.get("computed_market_value", r.get("market_value"))) for r in b_records)
        isin = a_records[0].get("isin") if a_records else (b_records[0].get("isin") if b_records else "")
        currency = a_records[0].get("currency") if a_records else None
        self.matches.append(
            {
                "pass_number": cfg.get("pass"),
                "pass_name": cfg.get("name"),
                "match_type": cfg.get("type"),
                "row_ids_a": [r["row_id"] for r in a_records],
                "row_ids_b": [r["row_id"] for r in b_records],
                "isin": isin,
                "currency": currency,
                "quantity_a": qty_a,
                "quantity_b": qty_b,
                "amount_a": amt_a,
                "amount_b": amt_b,
                "quantity_variance": round(qty_a - qty_b, 6),
                "amount_variance": round(amt_a - amt_b, 2),
            }
        )


def _field_a(rule: dict) -> str:
    return rule["field_a"]


def _field_b(rule: dict) -> str:
    return rule["field_b"]


def _num(value: Any) -> float:
    try:
        v = float(value)
        return 0.0 if v != v else v
    except (TypeError, ValueError):
        return 0.0
