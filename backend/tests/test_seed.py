"""P1 seed suite: the ReconOS securities dataset must contain every waterfall
pass fixture and every break scenario from the spec, exactly and reproducibly.
(docs/RECONOS_UPGRADE_PLAN.md §4 P1 acceptance criteria.)
"""
import json
from pathlib import Path

from app.seed.generator import (
    AUX_FILES,
    DEFAULT_CONFIG,
    LEGACY_FILES,
    SCENARIOS,
    SEED_FILES,
    assert_all_scenarios_present,
    generate,
    load_aux,
    write_seed,
)


def test_side_a_is_the_exact_25_row_spec_dataset():
    df_a, _, _ = generate()
    assert len(df_a) == 25
    assert list(df_a.columns) == [
        "trade_id", "isin", "quantity", "price", "currency", "settlement_date",
        "transaction_type", "account_id", "fund_id", "opening_quantity",
        "closing_quantity", "net_quantity", "status", "market_value", "dr_cr",
    ]
    # Row 20 is the deliberate duplicate of TRD001.
    assert (df_a["trade_id"] == "TRD001").sum() == 2
    # SELL rows carry CR + negative net movement.
    sells = df_a[df_a["transaction_type"] == "SELL"]
    assert set(sells["trade_id"]) == {"TRD004", "TRD011"}
    assert (sells["dr_cr"] == "CR").all()
    assert (sells["net_quantity"] < 0).all()
    # Zero-quantity rows.
    zeros = df_a[df_a["quantity"] == 0]
    assert set(zeros["trade_id"]) == set(SCENARIOS["zero_quantity_handled"])


def test_all_scenarios_present_self_check_passes():
    df_a, df_b, _ = generate()
    assert_all_scenarios_present(df_a, df_b)  # raises on any violation


def test_custody_side_shape():
    _, df_b, _ = generate()
    assert len(df_b) == 21
    assert list(df_b.columns) == [
        "reference", "isin", "quantity", "price", "currency", "posting_date",
        "account_id", "fund_id", "settlement_status", "market_value",
    ]


def test_pass_fixtures():
    _, df_b, _ = generate()
    # Pass 2: 2-day drift.
    assert set(df_b[df_b["posting_date"] == "2024-01-17"]["reference"]) == {"TRD006", "TRD007"}
    # Pass 3: quantity rounding 49999 vs 50000.
    assert df_b[df_b["reference"] == "TRD012"].iloc[0]["quantity"] == 49999
    # Pass 4: price rounding 245.68 vs 245.67.
    assert df_b[df_b["reference"] == "TRD013"].iloc[0]["price"] == 245.68
    # Pass 5: one-to-many split (two 15000 legs for TRD014's 30000).
    legs = df_b[df_b["isin"] == "GB00BH4HKS39"]
    assert len(legs) == 2 and legs["quantity"].sum() == 30000
    # Pass 6: many-to-one (6000+10000 -> 16000).
    assert df_b[df_b["isin"] == "US4592001014"].iloc[0]["quantity"] == 16000
    # Pass 7: subset sum (3000+7000 -> 10000).
    assert df_b[df_b["isin"] == "DE0005552004"].iloc[0]["quantity"] == 10000


def test_break_fixtures():
    df_a, df_b, _ = generate()
    # 3-day drift cluster: exactly the 4 Loop A trades post on 2024-01-18.
    drift = df_b[df_b["posting_date"] == "2024-01-18"]
    assert set(drift["reference"]) == set(SCENARIOS["break_3day_drift_loop_a"])
    # Missing leg: TRD019 ISIN absent from custody.
    assert (df_b["isin"] == "LU0323578657").sum() == 0
    # Duplicate posting pair on custody side.
    assert (df_b["reference"] == "TRD001").sum() == 2
    # Misbooking: custody row landed in ACC002 instead of ACC001.
    assert df_b[df_b["reference"] == "TRD021"].iloc[0]["account_id"] == "ACC002"
    # EMIR dispute: 16.5M vs 16.2M on a >15M position.
    a22 = df_a[df_a["trade_id"] == "TRD022"].iloc[0]
    b22 = df_b[df_b["reference"] == "TRD022"].iloc[0]
    assert a22["market_value"] == 16500000.00
    assert b22["market_value"] == 16200000.00
    assert a22["market_value"] - b22["market_value"] == 300000.00
    # Corporate action: TRD024 5000 -> 10000 after the seeded 2:1 split.
    b24 = df_b[df_b["reference"] == "TRD024"].iloc[0]
    assert b24["quantity"] == 10000 and b24["posting_date"] == "2024-01-10"
    # Zero-quantity trades have no custody legs.
    assert (df_b["isin"] == "GB00B3X7QG63").sum() == 0
    assert (df_b["isin"] == "US0231351067").sum() == 0


def test_aux_files_match_spec():
    aux = load_aux()
    assert set(AUX_FILES) == {
        "fx_rates.csv", "instrument_master.csv", "account_aliases.csv",
        "market_holidays.csv", "corporate_actions.csv", "cass_safeguarded.csv",
    }
    fx = aux["fx_rates"].set_index("currency")["rate_to_eur"]
    assert fx["USD"] == 0.9200 and fx["GBP"] == 1.1600 and fx["EUR"] == 1.0000
    assert len(aux["instrument_master"]) == 21
    assert len(aux["account_aliases"]) == 5
    assert len(aux["market_holidays"]) == 13
    ca = aux["corporate_actions"].iloc[0]
    assert ca["isin"] == "GB00B0YTLJ59" and ca["event_type"] == "STOCK_SPLIT" and ca["ratio"] == 2.0
    cass = aux["cass_safeguarded"]
    acc2 = cass[cass["client_account"] == "ACC002"].iloc[0]
    assert acc2["client_liability_eur"] - acc2["safeguarded_amount_eur"] == 5000.00


def test_default_config_v2_fields():
    cfg = DEFAULT_CONFIG
    assert cfg["recon_id"] == "recon_001"
    assert cfg["recon_name"] == "DB_PositionRecon_IBOR_vs_BNYMellon_Daily"
    assert cfg["recon_type"] == "POSITION"
    assert cfg["version"] == "1.0.0"
    assert cfg["status"] == "APPROVED"
    assert cfg["source_topology"] == "ONE_VS_ONE"
    assert len(cfg["auxiliary_files"]) == 5
    passes = cfg["matching_waterfall"]
    assert [p["pass"] for p in passes] == [1, 2, 3, 4, 5, 6, 7]
    assert passes[4]["type"] == "ONE_TO_MANY"
    assert passes[5]["type"] == "MANY_TO_ONE"
    assert passes[6]["type"] == "N_TO_M_SUBSET_SUM"
    assert cfg["position_control"]["enabled"] is True
    assert cfg["position_control"]["explained_break_categories"] == [
        "CORPORATE_ACTION", "PENDING_SETTLEMENT",
    ]
    emir = cfg["regulatory_config"]["emir"]
    assert emir["dispute_amount_threshold_eur"] == 15000000.00
    assert emir["dispute_days_threshold"] == 15
    cass = cfg["regulatory_config"]["cass"]
    assert cass["regime"] == "CASS_7A" and cass["reconciliation_frequency"] == "DAILY"
    auto = cfg["autonomy_config"]
    assert auto["stp_confidence_threshold"] == 0.90
    assert auto["write_off_auto_approve_below_eur"] == 500.00
    assert auto["write_off_dual_checker_above_eur"] == 10000.00
    assert cfg["output_hash_spec"]["hash_algorithm"] == "SHA256"


def test_write_seed_is_byte_identical_and_removes_legacy(tmp_path: Path):
    out1 = tmp_path / "run1"
    out2 = tmp_path / "run2"
    # Plant legacy files to confirm cleanup.
    out1.mkdir()
    for legacy in LEGACY_FILES:
        (out1 / legacy).write_text("legacy")

    write_seed(out1)
    write_seed(out2)

    for legacy in LEGACY_FILES:
        assert not (out1 / legacy).exists(), f"legacy file {legacy} must be removed"
    for name in SEED_FILES:
        b1 = (out1 / name).read_bytes()
        b2 = (out2 / name).read_bytes()
        assert b1 == b2, f"{name} not byte-identical across runs"

    cfg = json.loads((out1 / "default_config.json").read_text())
    assert cfg["recon_id"] == "recon_001"
