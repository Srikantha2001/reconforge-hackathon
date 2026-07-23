"""ReconOS engine v2 acceptance suite (P3 — docs/RECONOS_UPGRADE_PLAN.md §4).

Asserts the 7-pass waterfall resolves the seed exactly as the spec maps it,
that every break scenario surfaces, that TRD024 is a corporate-action explained
break, and that the run is reproducible (identical output hash).
"""
import pandas as pd
import pytest

from app.engine.business_days import business_day_diff
from app.engine.hashing import assign_row_ids
from app.engine.matching import MatchingWaterfall
from app.engine.subset_sum import SubsetSumMatcher
from app.engine.transforms import TransformPipeline
from app.engine.runner import reconcile
from app.seed.generator import generate, load_aux


@pytest.fixture(scope="module")
def result():
    df_a, df_b, cfg = generate()
    return reconcile(df_a, df_b, cfg, aux_data=load_aux())


# --- Waterfall: each pass matches its intended fixtures ---------------------

def _isins_at_pass(result, pass_no):
    return {m["isin"] for m in result.matches if m["pass_number"] == pass_no}


def test_pass_match_counts(result):
    counts = {p["pass_number"]: p["matched_count"] for p in result.pass_stats}
    assert counts == {1: 5, 2: 2, 3: 1, 4: 1, 5: 1, 6: 2, 7: 2}
    assert result.matched_count == 14


def test_pass_1_exact_matches(result):
    assert _isins_at_pass(result, 1) == {
        "GB00B0YTLJ59", "US0378331005", "DE0005140008", "FR0000131104", "NL0010273215",
    }


def test_pass_2_date_tolerance(result):
    assert _isins_at_pass(result, 2) == {"GB00B1YW4409", "US5949181045"}


def test_pass_3_quantity_rounding(result):
    assert _isins_at_pass(result, 3) == {"JP3633400001"}  # TRD012, 50000 vs 49999


def test_pass_4_price_rounding(result):
    assert _isins_at_pass(result, 4) == {"US88160R1014"}  # TRD013, 245.67 vs 245.68


def test_pass_5_one_to_many(result):
    m = next(m for m in result.matches if m["pass_number"] == 5)
    assert m["isin"] == "GB00BH4HKS39"
    assert len(m["row_ids_a"]) == 1 and len(m["row_ids_b"]) == 2  # TRD014 -> 2 custody legs
    assert m["quantity_a"] == 30000 and m["quantity_b"] == 30000


def test_pass_6_many_to_one(result):
    m = next(m for m in result.matches if m["pass_number"] == 6)
    assert m["isin"] == "US4592001014"
    assert len(m["row_ids_a"]) == 2 and len(m["row_ids_b"]) == 1  # TRD015+016 -> 1
    assert m["quantity_a"] == 16000


def test_pass_7_subset_sum(result):
    m = next(m for m in result.matches if m["pass_number"] == 7)
    assert m["isin"] == "DE0005552004"
    assert len(m["row_ids_a"]) == 2 and len(m["row_ids_b"]) == 1  # TRD017+018 -> 1
    assert m["quantity_a"] == 10000


# --- Breaks: every scenario surfaces correctly -----------------------------

def _break_by_isin(result, isin):
    return [b for b in result.breaks if b["isin"] == isin]


def test_open_break_count(result):
    assert result.break_count == 9


def test_duplicate_entry_flagged_both_sides(result):
    dups = [b for b in result.breaks if b["archetype"] == "duplicate_entry"]
    assert {b["side"] for b in dups} == {"A", "B"}
    assert all(b["isin"] == "GB00B0YTLJ59" for b in dups)  # TRD001 duplicate


def test_three_day_drift_breaks(result):
    drift_isins = {"DE000BAY0017", "CH0012221716", "IT0003128367", "ES0113211835"}  # TRD008-011
    for isin in drift_isins:
        brk = _break_by_isin(result, isin)
        assert len(brk) == 1
        assert brk[0]["side"] == "AB"
        assert brk[0]["deltas"].get("settlement_date:EXACT") == 3  # 3 business days


def test_missing_counterparty_leg(result):
    brk = _break_by_isin(result, "LU0323578657")  # TRD019
    assert len(brk) == 1
    assert brk[0]["side"] == "A"
    assert brk[0]["archetype"] == "missing_counterparty_leg"


def test_account_misbooking(result):
    brk = _break_by_isin(result, "IE00B4L5Y983")  # TRD021
    assert len(brk) == 1
    assert any(f["field_a"] == "account_id" for f in brk[0]["failed_rules"])


def test_emir_market_value_dispute(result):
    brk = _break_by_isin(result, "XS0149080666")  # TRD022
    assert len(brk) == 1
    assert brk[0]["deltas"].get("computed_market_value:EXACT") == 300000.0


def test_corporate_action_explained_not_open(result):
    # TRD024: 5000 vs 10000 explained by the 2:1 split, excluded from open breaks.
    open_gb = _break_by_isin(result, "GB00B0YTLJ59")
    assert all(b["archetype"] == "duplicate_entry" for b in open_gb)  # only the dup, not TRD024
    explained = result.explained_breaks
    assert len(explained) == 1
    assert explained[0]["break_key"] == "TRD024"
    assert explained[0]["explained_category"] == "CORPORATE_ACTION"


# --- Position proof --------------------------------------------------------

def test_position_proof(result):
    assert result.position_proof["A"]["status"] == "PROVED"
    assert result.position_proof["A"]["variance"] == 0.0
    assert result.position_proof["B"]["status"] == "NOT_APPLICABLE"


# --- Reproducibility (the critical gate) -----------------------------------

def test_reproducible_hash():
    df_a, df_b, cfg = generate()
    aux = load_aux()
    r1 = reconcile(df_a, df_b, cfg, aux_data=aux)
    r2 = reconcile(df_a, df_b, cfg, aux_data=aux)
    assert r1.output_hash == r2.output_hash
    assert len(r1.output_hash) == 64


# --- Unit tests: engine building blocks ------------------------------------

def test_business_day_diff_excludes_weekends():
    # 2024-01-15 is Monday; +2 business days -> Wednesday 01-17.
    assert business_day_diff("2024-01-15", "2024-01-17", set()) == 2
    assert business_day_diff("2024-01-15", "2024-01-18", set()) == 3
    # Friday 01-12 to Monday 01-15 spans a weekend -> 1 business day.
    assert business_day_diff("2024-01-12", "2024-01-15", set()) == 1


def test_business_day_diff_subtracts_holidays():
    # Insert 2024-01-16 as a holiday: 01-15 -> 01-17 now counts only 1.
    assert business_day_diff("2024-01-15", "2024-01-17", {"2024-01-16"}) == 1


def test_subset_sum_finds_group():
    a = assign_row_ids(pd.DataFrame({"isin": ["X", "X"], "quantity": [3000, 7000]}))
    b = assign_row_ids(pd.DataFrame({"isin": ["X"], "quantity": [10000]}))
    matcher = SubsetSumMatcher()
    matches = matcher.find_matches(a, b, "quantity", "quantity", tolerance=1.0, partition_col="isin")
    assert len(matches) == 1
    assert matches[0]["sum_a"] == 10000 and matches[0]["variance"] == 0


def test_transform_sign_flip_and_abs():
    df = pd.DataFrame({"quantity": [8000], "dr_cr": ["CR"]})
    out = TransformPipeline.apply(
        df,
        [
            {"step": 1, "op": "sign_flip", "column": "quantity", "condition": "dr_cr == 'CR'"},
            {"step": 2, "op": "abs_value", "column": "quantity"},
        ],
    )
    assert out["quantity"].iloc[0] == 8000


def test_transform_compute_market_value_and_strip_zeros():
    df = pd.DataFrame({"quantity": [1000], "price": [4.52], "trade_id": ["00TRD01"]})
    out = TransformPipeline.apply(
        df,
        [
            {"step": 1, "op": "compute_market_value", "quantity_col": "quantity",
             "price_col": "price", "output_col": "computed_market_value"},
            {"step": 2, "op": "strip_leading_zeros", "column": "trade_id"},
        ],
    )
    assert out["computed_market_value"].iloc[0] == 4520.0
    assert out["trade_id"].iloc[0] == "TRD01"


def test_numeric_tolerance_uses_decimal_precision():
    wf = MatchingWaterfall({"matching_waterfall": []})
    rule = {"field_a": "v", "field_b": "v", "match_type": "NUMERIC_TOLERANCE", "tolerance": 0.01}
    assert wf._check_value_rule({"v": "100.00"}, {"v": "100.01"}, rule)[0]
    assert not wf._check_value_rule({"v": "100.00"}, {"v": "100.02"}, rule)[0]


def test_none_value_fails_rule_never_raises():
    wf = MatchingWaterfall({"matching_waterfall": []})
    rule = {"field_a": "v", "field_b": "v", "match_type": "NUMERIC_TOLERANCE", "tolerance": 1}
    assert wf._check_value_rule({"v": None}, {"v": 5}, rule) == (False, None)
