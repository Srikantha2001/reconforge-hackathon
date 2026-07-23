"""ReconOS seed data generator (P1 — docs/RECONOS_UPGRADE_PLAN.md §4).

Produces the exact securities dataset from the ReconOS spec:

- ``internal_ibor.csv``      — 25 literal rows (TRD001–TRD025; row 20 is a
                               deliberate duplicate of TRD001; TRD023/TRD025
                               are zero-quantity rows).
- ``bny_mt535_custody.csv``  — custodian side, engineered so every matching
                               waterfall pass (1–7) and every break scenario
                               in the spec is exercised (see SCENARIOS).
- 6 auxiliary files          — fx_rates, instrument_master, account_aliases,
                               market_holidays, corporate_actions,
                               cass_safeguarded (verbatim from the spec).
- ``default_config.json``    — the v2 config (recon_001, version 1.0.0,
                               APPROVED) consumed by the P2 schema / P3 engine.

Everything is a literal — no RNG — so regeneration is byte-identical.
The self-check (`assert_all_scenarios_present`) is pure pandas and does NOT
run the matching engine: at P1 time the v2 engine does not exist yet.

Custodian ``reference`` values are not dictated by the spec; the convention
used here: exact/tolerance rows reuse the trade id; the TRD014 split legs are
``TRD014-A``/``TRD014-B``; the aggregated rows are ``TRD015-16`` and
``TRD017-18``; the duplicate custody posting reuses ``TRD001``.
"""
from __future__ import annotations

import argparse
import io
import json
from pathlib import Path
from typing import Any, Dict, Tuple

import pandas as pd

# --------------------------------------------------------------------------
# Side A — internal IBOR positions (25 exact rows from the spec).
# --------------------------------------------------------------------------
INTERNAL_IBOR_CSV = """\
trade_id,isin,quantity,price,currency,settlement_date,transaction_type,account_id,fund_id,opening_quantity,closing_quantity,net_quantity,status,market_value,dr_cr
TRD001,GB00B0YTLJ59,10000,4.52,GBP,2024-01-15,BUY,ACC001,FUND_A,100000,110000,10000,SETTLED,45200.00,DR
TRD002,US0378331005,5000,182.50,USD,2024-01-15,BUY,ACC001,FUND_A,50000,55000,5000,SETTLED,912500.00,DR
TRD003,DE0005140008,20000,10.23,EUR,2024-01-15,BUY,ACC002,FUND_B,200000,220000,20000,SETTLED,204600.00,DR
TRD004,FR0000131104,8000,65.40,EUR,2024-01-15,SELL,ACC002,FUND_B,80000,72000,-8000,SETTLED,523200.00,CR
TRD005,NL0010273215,15000,22.15,EUR,2024-01-15,BUY,ACC003,FUND_C,150000,165000,15000,SETTLED,332250.00,DR
TRD006,GB00B1YW4409,25000,8.75,GBP,2024-01-15,BUY,ACC001,FUND_A,250000,275000,25000,SETTLED,218750.00,DR
TRD007,US5949181045,12000,95.30,USD,2024-01-15,BUY,ACC001,FUND_A,120000,132000,12000,SETTLED,1143600.00,DR
TRD008,DE000BAY0017,7500,55.60,EUR,2024-01-15,BUY,ACC002,FUND_B,75000,82500,7500,SETTLED,417000.00,DR
TRD009,CH0012221716,3000,420.00,CHF,2024-01-15,BUY,ACC003,FUND_C,30000,33000,3000,SETTLED,1260000.00,DR
TRD010,IT0003128367,9500,3.85,EUR,2024-01-15,BUY,ACC002,FUND_B,95000,104500,9500,SETTLED,36575.00,DR
TRD011,ES0113211835,4200,6.12,EUR,2024-01-15,SELL,ACC003,FUND_C,42000,37800,-4200,SETTLED,25704.00,CR
TRD012,JP3633400001,50000,2.45,JPY,2024-01-15,BUY,ACC001,FUND_A,500000,550000,50000,SETTLED,122500.00,DR
TRD013,US88160R1014,1000,245.67,USD,2024-01-15,BUY,ACC002,FUND_B,10000,11000,1000,SETTLED,245670.00,DR
TRD014,GB00BH4HKS39,30000,15.80,GBP,2024-01-15,BUY,ACC003,FUND_C,300000,330000,30000,SETTLED,474000.00,DR
TRD015,US4592001014,6000,42.30,USD,2024-01-15,BUY,ACC001,FUND_A,60000,66000,6000,SETTLED,253800.00,DR
TRD016,US4592001014,10000,42.30,USD,2024-01-15,BUY,ACC001,FUND_A,100000,110000,10000,SETTLED,423000.00,DR
TRD017,DE0005552004,3000,88.50,EUR,2024-01-15,BUY,ACC002,FUND_B,30000,33000,3000,SETTLED,265500.00,DR
TRD018,DE0005552004,7000,88.50,EUR,2024-01-15,BUY,ACC002,FUND_B,70000,77000,7000,SETTLED,619500.00,DR
TRD019,LU0323578657,22000,5.60,EUR,2024-01-15,BUY,ACC003,FUND_C,220000,242000,22000,SETTLED,123200.00,DR
TRD001,GB00B0YTLJ59,10000,4.52,GBP,2024-01-15,BUY,ACC001,FUND_A,100000,110000,10000,SETTLED,45200.00,DR
TRD021,IE00B4L5Y983,11000,75.20,EUR,2024-01-15,BUY,ACC001,FUND_A,110000,121000,11000,SETTLED,827200.00,DR
TRD022,XS0149080666,500,33000.00,EUR,2024-01-15,BUY,ACC002,FUND_B,5000,5500,500,SETTLED,16500000.00,DR
TRD023,GB00B3X7QG63,0,125.00,GBP,2024-01-15,BUY,ACC003,FUND_C,0,0,0,SETTLED,0.00,DR
TRD024,GB00B0YTLJ59,5000,4.52,GBP,2024-01-10,BUY,ACC001,FUND_A,50000,55000,5000,SETTLED,22600.00,DR
TRD025,US0231351067,0,50.00,USD,2024-01-15,BUY,ACC001,FUND_A,0,0,0,SETTLED,0.00,DR
"""

# --------------------------------------------------------------------------
# Side B — BNY Mellon MT535 custody, engineered per the spec's scenario table.
# --------------------------------------------------------------------------
BNY_MT535_CUSTODY_CSV = """\
reference,isin,quantity,price,currency,posting_date,account_id,fund_id,settlement_status,market_value
TRD001,GB00B0YTLJ59,10000,4.52,GBP,2024-01-15,ACC001,FUND_A,SETTLED,45200.00
TRD002,US0378331005,5000,182.50,USD,2024-01-15,ACC001,FUND_A,SETTLED,912500.00
TRD003,DE0005140008,20000,10.23,EUR,2024-01-15,ACC002,FUND_B,SETTLED,204600.00
TRD004,FR0000131104,8000,65.40,EUR,2024-01-15,ACC002,FUND_B,SETTLED,523200.00
TRD005,NL0010273215,15000,22.15,EUR,2024-01-15,ACC003,FUND_C,SETTLED,332250.00
TRD006,GB00B1YW4409,25000,8.75,GBP,2024-01-17,ACC001,FUND_A,SETTLED,218750.00
TRD007,US5949181045,12000,95.30,USD,2024-01-17,ACC001,FUND_A,SETTLED,1143600.00
TRD008,DE000BAY0017,7500,55.60,EUR,2024-01-18,ACC002,FUND_B,SETTLED,417000.00
TRD009,CH0012221716,3000,420.00,CHF,2024-01-18,ACC003,FUND_C,SETTLED,1260000.00
TRD010,IT0003128367,9500,3.85,EUR,2024-01-18,ACC002,FUND_B,SETTLED,36575.00
TRD011,ES0113211835,4200,6.12,EUR,2024-01-18,ACC003,FUND_C,SETTLED,25704.00
TRD012,JP3633400001,49999,2.45,JPY,2024-01-15,ACC001,FUND_A,SETTLED,122497.55
TRD013,US88160R1014,1000,245.68,USD,2024-01-15,ACC002,FUND_B,SETTLED,245680.00
TRD014-A,GB00BH4HKS39,15000,15.80,GBP,2024-01-15,ACC003,FUND_C,SETTLED,237000.00
TRD014-B,GB00BH4HKS39,15000,15.80,GBP,2024-01-15,ACC003,FUND_C,SETTLED,237000.00
TRD015-16,US4592001014,16000,42.30,USD,2024-01-15,ACC001,FUND_A,SETTLED,676800.00
TRD017-18,DE0005552004,10000,88.50,EUR,2024-01-15,ACC002,FUND_B,SETTLED,885000.00
TRD001,GB00B0YTLJ59,10000,4.52,GBP,2024-01-15,ACC001,FUND_A,SETTLED,45200.00
TRD021,IE00B4L5Y983,11000,75.20,EUR,2024-01-15,ACC002,FUND_A,SETTLED,827200.00
TRD022,XS0149080666,500,32400.00,EUR,2024-01-15,ACC002,FUND_B,SETTLED,16200000.00
TRD024,GB00B0YTLJ59,10000,2.26,GBP,2024-01-10,ACC001,FUND_A,SETTLED,22600.00
"""

# --------------------------------------------------------------------------
# Auxiliary files — verbatim from the spec.
# --------------------------------------------------------------------------
AUX_FILES: Dict[str, str] = {
    "fx_rates.csv": """\
currency,rate_to_eur
USD,0.9200
GBP,1.1600
CHF,1.0500
JPY,0.0062
EUR,1.0000
""",
    "instrument_master.csv": """\
isin,sedol,cusip,bloomberg_ticker,currency,asset_class,exchange,settlement_days
GB00B0YTLJ59,B0YTLJ5,G3960C109,AZN LN,GBP,EQUITY,LSE,2
US0378331005,2046251,037833100,AAPL US,USD,EQUITY,NASDAQ,2
DE0005140008,5148006,DE0005140,DBK GR,EUR,EQUITY,XETRA,2
FR0000131104,4849601,FR0000131,BNP FP,EUR,EQUITY,EURONEXT,2
NL0010273215,BH4HKS3,NL0010273,ASML NA,EUR,EQUITY,EURONEXT,2
GB00B1YW4409,B1YW440,G5480U111,LLOY LN,GBP,EQUITY,LSE,2
US5949181045,2073390,594918104,MSFT US,USD,EQUITY,NASDAQ,2
DE000BAY0017,5478798,DE000BAY0,BAYN GR,EUR,EQUITY,XETRA,2
CH0012221716,7110388,CH0012221,NESN SW,CHF,EQUITY,SIX,2
IT0003128367,7108011,IT0003128,ENI IM,EUR,EQUITY,BORSA,2
ES0113211835,4172973,ES0113211,BBVA SM,EUR,EQUITY,BMEX,2
JP3633400001,6900643,JP3633400,7203 JT,JPY,EQUITY,TSE,2
US88160R1014,BYXZ778,88160R101,TSLA US,USD,EQUITY,NASDAQ,2
GB00BH4HKS39,BH4HKS3,G3981F108,HSBA LN,GBP,EQUITY,LSE,2
US4592001014,2090571,459200101,IBM US,USD,EQUITY,NYSE,2
DE0005552004,5552004,DE0005552,SAP GR,EUR,EQUITY,XETRA,2
LU0323578657,B29LN48,LU0323578,XTRMSCI LX,EUR,ETF,EURONEXT,2
IE00B4L5Y983,B4L5Y98,IE00B4L5Y,IWDA LN,EUR,ETF,LSE,2
XS0149080666,B149086,XS0149080,DB 5Y EUR,EUR,BOND,LSE,3
GB00B3X7QG63,B3X7QG6,G12994108,ULVR LN,GBP,EQUITY,LSE,2
US0231351067,2306701,023135106,AMZN US,USD,EQUITY,NASDAQ,2
""",
    "account_aliases.csv": """\
client_alias,canonical_id,client_name,currency
ACC001,DB_ACC_001_GBP,Alpha Capital,GBP
ACC002,DB_ACC_002_EUR,Beta Fund Management,EUR
ACC003,DB_ACC_003_EUR,Gamma Asset Managers,EUR
FUND_A,DB_FUND_ALPHA_001,Alpha Capital Main Fund,GBP
FUND_B,DB_FUND_BETA_002,Beta Equity Fund,EUR
""",
    "market_holidays.csv": """\
date,market,description
2024-01-01,TARGET2,New Year's Day
2024-03-29,TARGET2,Good Friday
2024-04-01,TARGET2,Easter Monday
2024-05-01,TARGET2,Labour Day
2024-12-25,TARGET2,Christmas Day
2024-12-26,TARGET2,Boxing Day
2024-01-01,LSE,New Year's Day
2024-03-29,LSE,Good Friday
2024-04-01,LSE,Easter Monday
2024-05-06,LSE,Early May Bank Holiday
2024-08-26,LSE,Summer Bank Holiday
2024-12-25,LSE,Christmas Day
2024-12-26,LSE,Boxing Day
""",
    "corporate_actions.csv": """\
isin,event_type,ex_date,pay_date,ratio,description
GB00B0YTLJ59,STOCK_SPLIT,2024-01-10,2024-01-10,2.0,2-for-1 stock split
""",
    "cass_safeguarded.csv": """\
client_account,fund_id,client_liability_eur,safeguarded_amount_eur,currency,reconciliation_date
ACC001,FUND_A,2500000.00,2500000.00,EUR,2024-01-15
ACC002,FUND_B,5000000.00,4995000.00,EUR,2024-01-15
ACC003,FUND_C,1800000.00,1800000.00,EUR,2024-01-15
""",
}

# --------------------------------------------------------------------------
# Config v2 — the shape the P2 schema formalizes and the P3 engine consumes.
# Also serves as the stub provider's authoring fallback (fallback ladder #3).
# --------------------------------------------------------------------------
DEFAULT_CONFIG: Dict[str, Any] = {
    "recon_id": "recon_001",
    "recon_name": "DB_PositionRecon_IBOR_vs_BNYMellon_Daily",
    "recon_type": "POSITION",
    "version": "1.0.0",
    "status": "APPROVED",
    "source_topology": "ONE_VS_ONE",
    "sources": [
        {
            "id": "src_a", "alias": "internal_ibor", "side": "A",
            "file": "internal_ibor.csv", "ingestion_type": "FILE_UPLOAD",
            "matching_unit": "QUANTITY", "sign_convention": "DEBIT_POSITIVE",
        },
        {
            "id": "src_b", "alias": "bny_mt535", "side": "B",
            "file": "bny_mt535_custody.csv", "ingestion_type": "FILE_UPLOAD",
            "matching_unit": "QUANTITY", "sign_convention": "DEBIT_POSITIVE",
        },
    ],
    "auxiliary_files": [
        {"id": "aux_fx", "alias": "fx_rates", "file": "fx_rates.csv", "key_column": "currency"},
        {"id": "aux_instruments", "alias": "instrument_master", "file": "instrument_master.csv", "key_column": "isin"},
        {"id": "aux_accounts", "alias": "account_aliases", "file": "account_aliases.csv", "key_column": "client_alias"},
        {"id": "aux_holidays", "alias": "market_holidays", "file": "market_holidays.csv", "key_column": "date"},
        {"id": "aux_corp_actions", "alias": "corporate_actions", "file": "corporate_actions.csv", "key_column": "isin"},
    ],
    "transforms": {
        "side_a": [
            {"step": 1, "op": "sign_flip", "column": "quantity", "condition": "dr_cr == 'CR'"},
            {"step": 2, "op": "abs_value", "column": "quantity"},
            {"step": 3, "op": "upper_case", "column": "isin"},
            {"step": 4, "op": "date_normalise", "column": "settlement_date", "input_format": "%Y-%m-%d"},
            {"step": 5, "op": "strip_leading_zeros", "column": "trade_id"},
            {"step": 6, "op": "compute_market_value", "quantity_col": "quantity", "price_col": "price", "output_col": "computed_market_value"},
        ],
        "side_b": [
            {"step": 1, "op": "upper_case", "column": "isin"},
            {"step": 2, "op": "date_normalise", "column": "posting_date", "input_format": "%Y-%m-%d"},
            {"step": 3, "op": "strip_leading_zeros", "column": "reference"},
            {"step": 4, "op": "compute_market_value", "quantity_col": "quantity", "price_col": "price", "output_col": "computed_market_value"},
        ],
    },
    "position_control": {
        "enabled": True,
        "side_a": {
            "opening_balance_field": "opening_quantity",
            "closing_balance_field": "closing_quantity",
            "movement_field": "net_quantity",
            "balance_type": "QUANTITY",
        },
        "side_b": {
            "opening_balance_field": None,
            "closing_balance_field": None,
            "movement_field": None,
            "balance_type": "QUANTITY",
        },
        "tolerance": 0.0,
        "explained_break_categories": ["CORPORATE_ACTION", "PENDING_SETTLEMENT"],
    },
    "matching_waterfall": [
        {
            "pass": 1, "name": "Exact ISIN + quantity + value + date + account", "type": "ONE_TO_ONE",
            "key_rules": [{"field_a": "isin", "field_b": "isin", "match_type": "EXACT"}],
            "value_rules": [
                {"field_a": "quantity", "field_b": "quantity", "match_type": "EXACT"},
                {"field_a": "computed_market_value", "field_b": "computed_market_value", "match_type": "EXACT"},
                {"field_a": "settlement_date", "field_b": "posting_date", "match_type": "EXACT"},
                {"field_a": "account_id", "field_b": "account_id", "match_type": "EXACT"},
            ],
        },
        {
            "pass": 2, "name": "Settlement date tolerance (2 business days)", "type": "ONE_TO_ONE",
            "key_rules": [{"field_a": "isin", "field_b": "isin", "match_type": "EXACT"}],
            "value_rules": [
                {"field_a": "quantity", "field_b": "quantity", "match_type": "EXACT"},
                {"field_a": "computed_market_value", "field_b": "computed_market_value", "match_type": "EXACT"},
                {"field_a": "settlement_date", "field_b": "posting_date", "match_type": "DATE_TOLERANCE",
                 "tolerance_days": 2, "business_days_only": True, "calendar_market": "TARGET2"},
                {"field_a": "account_id", "field_b": "account_id", "match_type": "EXACT"},
            ],
        },
        {
            "pass": 3, "name": "Quantity rounding tolerance (1 unit)", "type": "ONE_TO_ONE",
            "key_rules": [{"field_a": "isin", "field_b": "isin", "match_type": "EXACT"}],
            "value_rules": [
                {"field_a": "quantity", "field_b": "quantity", "match_type": "NUMERIC_TOLERANCE", "tolerance": 1.0},
                # A rounding-scale market-value guard so a 1-unit quantity
                # rounding still ties out on value, but a genuine price/value
                # dispute (e.g. the EMIR break) is NOT silently matched here.
                {"field_a": "computed_market_value", "field_b": "computed_market_value",
                 "match_type": "NUMERIC_TOLERANCE", "tolerance": 5.0},
                {"field_a": "settlement_date", "field_b": "posting_date", "match_type": "DATE_TOLERANCE",
                 "tolerance_days": 2, "business_days_only": True, "calendar_market": "TARGET2"},
                {"field_a": "account_id", "field_b": "account_id", "match_type": "EXACT"},
            ],
        },
        {
            "pass": 4, "name": "Price/FX rounding tolerance on market value", "type": "ONE_TO_ONE",
            "key_rules": [{"field_a": "isin", "field_b": "isin", "match_type": "EXACT"}],
            "value_rules": [
                {"field_a": "quantity", "field_b": "quantity", "match_type": "EXACT"},
                {"field_a": "computed_market_value", "field_b": "computed_market_value",
                 "match_type": "NUMERIC_TOLERANCE", "tolerance": 25.00},
                {"field_a": "settlement_date", "field_b": "posting_date", "match_type": "DATE_TOLERANCE",
                 "tolerance_days": 2, "business_days_only": True, "calendar_market": "TARGET2"},
                {"field_a": "account_id", "field_b": "account_id", "match_type": "EXACT"},
            ],
        },
        {
            "pass": 5, "name": "One-to-many split settlement", "type": "ONE_TO_MANY",
            "key_rules": [{"field_a": "isin", "field_b": "isin", "match_type": "EXACT"}],
            "restrict_isins": ["GB00BH4HKS39"],
            "group_by_b": ["isin"],
            "aggregate_field_b": "quantity",
            "aggregate_op": "SUM",
            "value_rules": [
                {"field_a": "quantity", "field_b": "quantity", "match_type": "NUMERIC_TOLERANCE", "tolerance": 0.0},
            ],
        },
        {
            "pass": 6, "name": "Many-to-one aggregate", "type": "MANY_TO_ONE",
            "key_rules": [{"field_a": "isin", "field_b": "isin", "match_type": "EXACT"}],
            "restrict_isins": ["US4592001014"],
            "group_by_a": ["isin"],
            "aggregate_field_a": "quantity",
            "aggregate_op": "SUM",
            "value_rules": [
                {"field_a": "quantity", "field_b": "quantity", "match_type": "NUMERIC_TOLERANCE", "tolerance": 0.0},
            ],
        },
        {
            "pass": 7, "name": "N-to-M subset sum", "type": "N_TO_M_SUBSET_SUM",
            "restrict_isins": ["DE0005552004"],
            "value_field_a": "quantity",
            "value_field_b": "quantity",
            "partition_col": "isin",
            "tolerance": 1.0,
            "performance_guard": {
                "max_group_size": 4,
                "max_rows_per_partition": 50,
                "timeout_seconds": 30,
            },
        },
    ],
    "regulatory_config": {
        "emir": {
            "enabled": True,
            "dispute_amount_threshold_eur": 15000000.00,
            "dispute_days_threshold": 15,
            "auto_generate_notification": True,
            "competent_authority": "BaFin",
        },
        "cass": {
            "enabled": True,
            "regime": "CASS_7A",
            "reconciliation_frequency": "DAILY",
            "shortfall_escalation_threshold_eur": 1000.00,
        },
    },
    "autonomy_config": {
        "stp_confidence_threshold": 0.90,
        "write_off_auto_approve_below_eur": 500.00,
        "write_off_dual_checker_above_eur": 10000.00,
        "maker_checker_same_person_allowed": False,
        "pending_approval_expiry_hours": 24,
    },
    "output_hash_spec": {
        "hash_algorithm": "SHA256",
        "amount_format": "2_decimal_string",
        "quantity_format": "6_decimal_string",
        "date_format": "%Y-%m-%d",
    },
}

# --------------------------------------------------------------------------
# Scenario table — single source of truth for the self-check and the tests.
# Trade ids refer to side A; "row 20" of side A is the TRD001 duplicate.
# --------------------------------------------------------------------------
SCENARIOS: Dict[str, Any] = {
    "pass_1_exact": ["TRD001", "TRD002", "TRD003", "TRD004", "TRD005"],
    "pass_2_date_drift_2d": ["TRD006", "TRD007"],
    "pass_3_qty_rounding": ["TRD012"],
    "pass_4_price_rounding": ["TRD013"],
    "pass_5_one_to_many": ["TRD014"],
    "pass_6_many_to_one": ["TRD015", "TRD016"],
    "pass_7_subset_sum": ["TRD017", "TRD018"],
    "break_3day_drift_loop_a": ["TRD008", "TRD009", "TRD010", "TRD011"],
    "break_missing_leg": ["TRD019"],
    "break_duplicate": ["TRD001"],  # duplicated on BOTH sides
    "break_misbooking": ["TRD021"],
    "break_emir_dispute": ["TRD022"],
    "explained_corporate_action": ["TRD024"],
    "zero_quantity_handled": ["TRD023", "TRD025"],
}

SEED_FILES = ["internal_ibor.csv", "bny_mt535_custody.csv", "default_config.json"] + list(AUX_FILES)
LEGACY_FILES = ["ledger.csv", "statement.csv"]  # pre-ReconOS seed pair — removed on write


def generate() -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    """Return (side A frame, side B frame, default config) parsed from the literals."""
    df_a = pd.read_csv(io.StringIO(INTERNAL_IBOR_CSV))
    df_b = pd.read_csv(io.StringIO(BNY_MT535_CUSTODY_CSV))
    return df_a, df_b, DEFAULT_CONFIG


def load_aux() -> Dict[str, pd.DataFrame]:
    """Parse every auxiliary file literal into a DataFrame, keyed by alias."""
    return {
        name.replace(".csv", ""): pd.read_csv(io.StringIO(content))
        for name, content in AUX_FILES.items()
    }


def assert_all_scenarios_present(df_a: pd.DataFrame, df_b: pd.DataFrame) -> None:
    """Pure-pandas structural self-check of every pass/break scenario.

    Raises AssertionError with a specific message on the first violation so a
    broken generator fails loudly at generation time, not at demo time.
    """
    def _one(frame: pd.DataFrame, mask: pd.Series, what: str) -> pd.Series:
        rows = frame[mask]
        assert len(rows) == 1, f"{what}: expected exactly 1 row, found {len(rows)}"
        return rows.iloc[0]

    # Side A shape: 25 rows, TRD001 duplicated (rows 1 & 20), two zero-qty rows.
    assert len(df_a) == 25, f"internal_ibor must have 25 rows, has {len(df_a)}"
    assert (df_a["trade_id"] == "TRD001").sum() == 2, "TRD001 must appear twice on side A (row 20 duplicate)"
    for tid in SCENARIOS["zero_quantity_handled"]:
        row = _one(df_a, df_a["trade_id"] == tid, f"zero-quantity row {tid}")
        assert row["quantity"] == 0 and row["market_value"] == 0.0, f"{tid} must be zero-quantity/zero-value"

    # Pass 1 — exact matches: identical isin/quantity/date/account on both sides.
    # TRD001 deliberately appears twice on each side (duplicate scenario), so
    # its expected custody count is 2; every other pass-1 fixture is unique.
    for tid in SCENARIOS["pass_1_exact"]:
        a = df_a[df_a["trade_id"] == tid].iloc[0]
        rows_b = df_b[df_b["reference"] == tid]
        expected = 2 if tid == "TRD001" else 1
        assert len(rows_b) == expected, (
            f"pass-1 custody row {tid}: expected {expected} row(s), found {len(rows_b)}"
        )
        b = rows_b.iloc[0]
        assert b["quantity"] == abs(a["quantity"]) and b["posting_date"] == a["settlement_date"], (
            f"{tid} must match exactly on quantity and date"
        )

    # Pass 2 — 2-day drift: posting_date = 2024-01-17.
    for tid in SCENARIOS["pass_2_date_drift_2d"]:
        b = _one(df_b, df_b["reference"] == tid, f"pass-2 custody row {tid}")
        assert b["posting_date"] == "2024-01-17", f"{tid} custody must post on 2024-01-17 (2-day drift)"

    # Pass 3 — quantity rounding: TRD012 custody quantity 49999 vs 50000.
    b = _one(df_b, df_b["reference"] == "TRD012", "pass-3 custody row TRD012")
    assert b["quantity"] == 49999, "TRD012 custody quantity must be 49999 (rounding)"

    # Pass 4 — price rounding: TRD013 custody price 245.68 vs 245.67.
    b = _one(df_b, df_b["reference"] == "TRD013", "pass-4 custody row TRD013")
    assert b["price"] == 245.68, "TRD013 custody price must be 245.68 (FX/price rounding)"

    # Pass 5 — one-to-many: two custody legs of 15000 summing to TRD014's 30000.
    legs = df_b[df_b["isin"] == "GB00BH4HKS39"]
    legs = legs[legs["posting_date"] == "2024-01-15"]
    assert len(legs) == 2 and set(legs["quantity"]) == {15000}, (
        "TRD014 must split into two 15000 custody legs"
    )
    assert legs["quantity"].sum() == 30000

    # Pass 6 — many-to-one: TRD015 (6000) + TRD016 (10000) vs one 16000 custody row.
    b = _one(df_b, df_b["isin"] == "US4592001014", "pass-6 custody row for TRD015+TRD016")
    assert b["quantity"] == 16000, "TRD015+TRD016 custody aggregate must be 16000"

    # Pass 7 — N-M subset: TRD017 (3000) + TRD018 (7000) vs one 10000 custody row.
    b = _one(df_b, df_b["isin"] == "DE0005552004", "pass-7 custody row for TRD017+TRD018")
    assert b["quantity"] == 10000, "TRD017+TRD018 custody aggregate must be 10000"

    # Breaks — 3-day drift cluster (Loop A signal: 4 occurrences).
    for tid in SCENARIOS["break_3day_drift_loop_a"]:
        b = _one(df_b, df_b["reference"] == tid, f"drift custody row {tid}")
        assert b["posting_date"] == "2024-01-18", f"{tid} custody must post on 2024-01-18 (3-day drift)"

    # Break — missing leg: no custody row for TRD019's ISIN.
    assert (df_b["isin"] == "LU0323578657").sum() == 0, "TRD019 (LU0323578657) must have no custody row"

    # Break — duplicate posting on both sides.
    assert (df_b["reference"] == "TRD001").sum() == 2, "custody must contain a duplicate TRD001 posting"

    # Break — misbooking: TRD021 custody booked to ACC002 instead of ACC001.
    b = _one(df_b, df_b["reference"] == "TRD021", "misbooking custody row TRD021")
    assert b["account_id"] == "ACC002", "TRD021 custody must be misbooked to ACC002"

    # Break — EMIR dispute: TRD022 custody value 16,200,000 vs 16,500,000 (>15M).
    b = _one(df_b, df_b["reference"] == "TRD022", "EMIR custody row TRD022")
    a = df_a[df_a["trade_id"] == "TRD022"].iloc[0]
    assert b["market_value"] == 16200000.00 and a["market_value"] == 16500000.00, (
        "TRD022 must show a 300,000 dispute on a >15M position"
    )
    assert a["market_value"] > 15000000.00, "TRD022 must exceed the EMIR 15M threshold"

    # Explained by corporate action: TRD024 5000 -> 10000 after the 2:1 split.
    b = _one(
        df_b,
        (df_b["reference"] == "TRD024") & (df_b["posting_date"] == "2024-01-10"),
        "corporate-action custody row TRD024",
    )
    assert b["quantity"] == 10000, "TRD024 custody quantity must be 10000 (post 2-for-1 split)"
    ca = load_aux()["corporate_actions"]
    assert ((ca["isin"] == "GB00B0YTLJ59") & (ca["ratio"] == 2.0)).any(), (
        "corporate_actions must contain the GB00B0YTLJ59 2-for-1 split"
    )

    # Zero-quantity rows have no custody legs.
    assert (df_b["isin"] == "GB00B3X7QG63").sum() == 0, "TRD023 must have no custody row"
    assert (df_b["isin"] == "US0231351067").sum() == 0, "TRD025 must have no custody row"

    # CASS aux — the seeded ACC002 shortfall of 5,000 EUR.
    cass = load_aux()["cass_safeguarded"]
    acc2 = cass[cass["client_account"] == "ACC002"].iloc[0]
    shortfall = acc2["client_liability_eur"] - acc2["safeguarded_amount_eur"]
    assert shortfall == 5000.00, f"ACC002 CASS shortfall must be 5,000 EUR, got {shortfall}"


def write_seed(out_dir: Path) -> None:
    """Write every seed file (byte-identical on re-run) and remove legacy files."""
    out_dir.mkdir(parents=True, exist_ok=True)
    df_a, df_b, config = generate()
    assert_all_scenarios_present(df_a, df_b)

    (out_dir / "internal_ibor.csv").write_text(INTERNAL_IBOR_CSV)
    (out_dir / "bny_mt535_custody.csv").write_text(BNY_MT535_CUSTODY_CSV)
    for name, content in AUX_FILES.items():
        (out_dir / name).write_text(content)
    (out_dir / "default_config.json").write_text(json.dumps(config, indent=2) + "\n")

    for legacy in LEGACY_FILES:
        path = out_dir / legacy
        if path.exists():
            path.unlink()

    print(
        f"Seed written to {out_dir}: {len(df_a)} IBOR rows, {len(df_b)} custody rows, "
        f"{len(AUX_FILES)} aux files, default_config.json (v2)."
    )
    print("All 7 waterfall-pass fixtures and every break scenario verified present.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate ReconOS seed data.")
    parser.add_argument("--out", type=str, default="./data", help="Output directory")
    args = parser.parse_args()
    write_seed(Path(args.out))


if __name__ == "__main__":
    main()
