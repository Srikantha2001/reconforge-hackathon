"""Deterministic engine: transforms -> key match -> rule eval, and the
reproducibility contract (§2 law 4: same input -> identical output hash)."""
import pandas as pd
import pytest

from app.engine.runner import reconcile

CONFIG = {
    "recon_name": "Test",
    "source_a": {"alias": "ledger", "key_columns": ["trade_id"]},
    "source_b": {"alias": "statement", "key_columns": ["ref"]},
    "transforms": [{"field": "amount", "op": "abs"}, {"field": "ccy", "op": "upper"}],
    "match_rules": [
        {"field_a": "trade_id", "field_b": "ref", "type": "exact"},
        {"field_a": "amount", "field_b": "amount", "type": "numeric_tolerance", "tolerance": 0.01},
        {"field_a": "value_date", "field_b": "value_date", "type": "date_tolerance", "tolerance_days": 2},
    ],
}


def _basic_frames():
    df_a = pd.DataFrame(
        [
            {"trade_id": "T1", "amount": 100.00, "ccy": "usd", "value_date": "2026-07-01"},
            {"trade_id": "T2", "amount": -50.00, "ccy": "USD", "value_date": "2026-07-02"},
            {"trade_id": "T3", "amount": 200.00, "ccy": "USD", "value_date": "2026-07-05"},
        ]
    )
    df_b = pd.DataFrame(
        [
            {"ref": "T1", "amount": 100.005, "ccy": "USD", "value_date": "2026-07-01"},
            {"ref": "T2", "amount": 50.00, "ccy": "USD", "value_date": "2026-07-04"},
            {"ref": "T4", "amount": 999.00, "ccy": "USD", "value_date": "2026-07-05"},
        ]
    )
    return df_a, df_b


def test_clean_and_tolerance_matches():
    df_a, df_b = _basic_frames()
    result = reconcile(df_a, df_b, CONFIG)
    matched_keys = {m["key"] for m in result.matched}
    assert matched_keys == {"T1", "T2"}
    assert result.matched_count == 2


def test_transform_abs_normalizes_sign():
    # T2 ledger amount is -50, statement is +50 — only matches because of abs().
    df_a, df_b = _basic_frames()
    result = reconcile(df_a, df_b, CONFIG)
    assert any(m["key"] == "T2" for m in result.matched)


def test_one_sided_breaks_for_unmatched_keys():
    df_a, df_b = _basic_frames()
    result = reconcile(df_a, df_b, CONFIG)
    sides = {b["break_key"]: b["side"] for b in result.breaks}
    assert sides["T3"] == "one_sided_a"
    assert sides["T4"] == "one_sided_b"


def test_reproducibility_identical_hash_same_input():
    df_a, df_b = _basic_frames()
    r1 = reconcile(df_a, df_b, CONFIG)
    r2 = reconcile(df_a, df_b, CONFIG)
    assert r1.output_hash == r2.output_hash


def test_reproducibility_hash_changes_with_different_input():
    df_a, df_b = _basic_frames()
    r1 = reconcile(df_a, df_b, CONFIG)
    df_b_mutated = df_b.copy()
    df_b_mutated.loc[0, "amount"] = 999.99
    r2 = reconcile(df_a, df_b_mutated, CONFIG)
    assert r1.output_hash != r2.output_hash


def test_duplicate_entry_detection():
    df_a = pd.DataFrame([{"trade_id": "D1", "amount": 100.0, "ccy": "USD", "value_date": "2026-07-01"}])
    df_b = pd.DataFrame(
        [
            {"ref": "D1", "amount": 100.0, "ccy": "USD", "value_date": "2026-07-01"},
            {"ref": "D1", "amount": 100.0, "ccy": "USD", "value_date": "2026-07-01"},
        ]
    )
    result = reconcile(df_a, df_b, CONFIG)
    assert result.matched_count == 1
    dup_breaks = [b for b in result.breaks if b["archetype"] == "duplicate_entry"]
    assert len(dup_breaks) == 1


def test_partial_fill_ratio_heuristic():
    df_a = pd.DataFrame([{"trade_id": "P1", "amount": 300.0, "ccy": "USD", "value_date": "2026-07-01"}])
    df_b = pd.DataFrame([{"ref": "P1", "amount": 150.0, "ccy": "USD", "value_date": "2026-07-01"}])
    result = reconcile(df_a, df_b, CONFIG)
    assert result.breaks[0]["archetype"] == "partial_fill"


def test_reference_format_mismatch_fuzzy_merge():
    df_a = pd.DataFrame([{"trade_id": "TRD-1042", "amount": 200.0, "ccy": "USD", "value_date": "2026-07-05"}])
    df_b = pd.DataFrame([{"ref": "trd1042", "amount": 200.0, "ccy": "USD", "value_date": "2026-07-05"}])
    result = reconcile(df_a, df_b, CONFIG)
    assert result.matched_count == 0
    assert len(result.breaks) == 1
    assert result.breaks[0]["archetype"] == "reference_format_mismatch"
    assert result.breaks[0]["row_a"] is not None and result.breaks[0]["row_b"] is not None


def test_wrong_account_reference():
    cfg = {**CONFIG, "match_rules": CONFIG["match_rules"] + [
        {"field_a": "account", "field_b": "account", "type": "exact"}
    ]}
    df_a = pd.DataFrame(
        [{"trade_id": "W1", "amount": 100.0, "ccy": "USD", "value_date": "2026-07-01", "account": "ACC-1"}]
    )
    df_b = pd.DataFrame(
        [{"ref": "W1", "amount": 100.0, "ccy": "USD", "value_date": "2026-07-01", "account": "ACC-2"}]
    )
    result = reconcile(df_a, df_b, cfg)
    assert result.breaks[0]["archetype"] == "wrong_account_reference"


def test_amount_outside_tolerance_vs_partial_fill_distinction():
    df_a = pd.DataFrame([{"trade_id": "A1", "amount": 1618.0, "ccy": "USD", "value_date": "2026-07-01"}])
    df_b = pd.DataFrame([{"ref": "A1", "amount": 1755.42, "ccy": "USD", "value_date": "2026-07-01"}])
    result = reconcile(df_a, df_b, CONFIG)
    assert result.breaks[0]["archetype"] == "amount_outside_tolerance"


def test_severity_bands_missing_leg_is_high():
    # An old one-sided row (reference_date is set by the *other*, more recent
    # clean pair) should read as a genuinely missing leg -> high severity —
    # distinct from a *recent* one-sided row, which reads as a timing lag.
    df_a = pd.DataFrame(
        [
            {"trade_id": "CLEAN", "amount": 10.0, "ccy": "USD", "value_date": "2026-07-20"},
            {"trade_id": "H1", "amount": 1000.0, "ccy": "USD", "value_date": "2026-06-01"},
        ]
    )
    df_b = pd.DataFrame([{"ref": "CLEAN", "amount": 10.0, "ccy": "USD", "value_date": "2026-07-20"}])
    result = reconcile(df_a, df_b, CONFIG)
    h1_break = next(b for b in result.breaks if b["break_key"] == "H1")
    assert h1_break["archetype"] == "missing_counterparty_leg"
    assert h1_break["severity"] == "high"


def test_severity_bands_recent_one_sided_is_timing_lag():
    df_a = pd.DataFrame(
        [
            {"trade_id": "CLEAN", "amount": 10.0, "ccy": "USD", "value_date": "2026-07-20"},
            {"trade_id": "LAG1", "amount": 500.0, "ccy": "USD", "value_date": "2026-07-20"},
        ]
    )
    df_b = pd.DataFrame([{"ref": "CLEAN", "amount": 10.0, "ccy": "USD", "value_date": "2026-07-20"}])
    result = reconcile(df_a, df_b, CONFIG)
    lag_break = next(b for b in result.breaks if b["break_key"] == "LAG1")
    assert lag_break["archetype"] == "timing_settlement_lag"
    assert lag_break["severity"] == "medium"
