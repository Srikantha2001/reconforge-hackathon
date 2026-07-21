"""Seed data generator for ReconForge.

Produces a rehearsed ledger/statement CSV pair that deliberately contains at
least one instance of each of the 10 break archetypes (§7) plus a 3-day
settlement-drift cluster for Loop A to discover — and asserts that at
generation time so a broken generator fails loudly instead of demoing badly.

Also emits the pre-approved fallback config (fallback ladder rung #3): if LLM
authoring is flaky, the app can still run this seed pair against a known-good
config and show the rest of the pipeline (run -> reproducibility -> agents ->
loop).
"""
from __future__ import annotations

import argparse
import json
import random
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd

from ..engine.runner import reconcile

SEED = 42
MAX_DATE = date(2026, 7, 20)  # "as of" date for the recency/timing-lag heuristic
OLD_DATE = MAX_DATE - timedelta(days=30)

ACCOUNTS = ["ACC-001", "ACC-002", "ACC-003", "ACC-004", "ACC-005", "ACC-006"]
COUNTERPARTIES = ["Acme Corp", "Globex Ltd", "Initech", "Umbrella Inc", "Soylent Co", "Hooli"]

DEFAULT_CONFIG: Dict[str, Any] = {
    "recon_name": "Nostro_USD_Daily",
    "source_a": {"alias": "ledger", "key_columns": ["trade_id"]},
    "source_b": {"alias": "statement", "key_columns": ["ref"]},
    "transforms": [
        {"field": "amount", "op": "abs"},
        {"field": "ccy", "op": "upper"},
    ],
    "match_rules": [
        {"field_a": "trade_id", "field_b": "ref", "type": "exact"},
        {"field_a": "amount", "field_b": "amount", "type": "numeric_tolerance", "tolerance": 0.01},
        {"field_a": "value_date", "field_b": "value_date", "type": "date_tolerance", "tolerance_days": 2},
        {"field_a": "account", "field_b": "account", "type": "exact"},
    ],
}

# Expected archetype per injected trade_id-prefix group, used for the
# generation-time self-check and reused by the test suite.
EXPECTED_ARCHETYPES = {
    "value_date_mismatch",
    "fx_rounding_diff",
    "partial_fill",
    "duplicate_entry",
    "fee_charge_diff",
    "timing_settlement_lag",
    "wrong_account_reference",
    "missing_counterparty_leg",
    "amount_outside_tolerance",
    "reference_format_mismatch",
}


def _rng() -> random.Random:
    return random.Random(SEED)


def generate() -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    rng = _rng()
    ledger: List[Dict[str, Any]] = []
    statement: List[Dict[str, Any]] = []

    def rand_date(base: date, spread_days: int = 25) -> date:
        return base - timedelta(days=rng.randint(0, spread_days))

    def add_clean(idx: int) -> None:
        trade_id = f"CLN{idx:04d}"
        amount = round(rng.uniform(50, 5000), 2)
        ccy = rng.choice(["USD", "USD", "USD", "EUR", "GBP"])
        vdate = rand_date(MAX_DATE, 20)
        account = rng.choice(ACCOUNTS)
        cp = rng.choice(COUNTERPARTIES)
        ledger.append(
            {
                "trade_id": trade_id, "amount": amount, "ccy": ccy.lower(),
                "value_date": vdate.isoformat(), "account": account, "counterparty": cp,
            }
        )
        statement.append(
            {
                "ref": trade_id, "amount": amount, "ccy": ccy,
                "value_date": vdate.isoformat(), "account": account,
                "description": f"Settlement for {cp}",
            }
        )

    # 1) 55 clean one-to-one matches.
    for i in range(1, 56):
        add_clean(i)

    # 2) Archetype #1 + systemic signal: 3-day settlement-drift cluster (5 breaks).
    for i in range(1, 6):
        trade_id = f"DRF{i:04d}"
        amount = round(rng.uniform(100, 3000), 2)
        vdate = MAX_DATE - timedelta(days=10 + i)
        account = rng.choice(ACCOUNTS)
        ledger.append(
            {
                "trade_id": trade_id, "amount": amount, "ccy": "USD",
                "value_date": vdate.isoformat(), "account": account,
                "counterparty": rng.choice(COUNTERPARTIES),
            }
        )
        statement.append(
            {
                "ref": trade_id, "amount": amount, "ccy": "USD",
                "value_date": (vdate + timedelta(days=3)).isoformat(), "account": account,
                "description": "Settlement (delayed)",
            }
        )

    # 3) Archetype #2: FX rounding / conversion diff (2 rows, delta <= 0.05).
    # Fixed (not random) amounts: these rows exist to hit a specific
    # classifier branch, and a random amount could coincidentally produce a
    # ratio close to a "nice fraction" and get misread as partial_fill.
    for i, (amount, delta) in enumerate(((915.50, 0.02), (1204.75, 0.04)), start=1):
        trade_id = f"FXR{i:04d}"
        vdate = rand_date(MAX_DATE, 15)
        account = rng.choice(ACCOUNTS)
        ledger.append(
            {"trade_id": trade_id, "amount": amount, "ccy": "USD",
             "value_date": vdate.isoformat(), "account": account,
             "counterparty": rng.choice(COUNTERPARTIES)}
        )
        statement.append(
            {"ref": trade_id, "amount": round(amount + delta, 2), "ccy": "USD",
             "value_date": vdate.isoformat(), "account": account,
             "description": "FX-converted settlement"}
        )

    # 4) Archetype #3: partial fill — one ledger row vs two statement legs that
    #    individually mismatch the anchor amount by a clean ~0.5 ratio.
    pfl_amount = 300.00
    pfl_vdate = rand_date(MAX_DATE, 15)
    pfl_account = rng.choice(ACCOUNTS)
    ledger.append(
        {"trade_id": "PFL0001", "amount": pfl_amount, "ccy": "USD",
         "value_date": pfl_vdate.isoformat(), "account": pfl_account,
         "counterparty": rng.choice(COUNTERPARTIES)}
    )
    for _ in range(2):
        statement.append(
            {"ref": "PFL0001", "amount": pfl_amount / 2, "ccy": "USD",
             "value_date": pfl_vdate.isoformat(), "account": pfl_account,
             "description": "Partial settlement leg"}
        )

    # 5) Archetype #4: duplicate entry — one ledger row, two identical statement postings.
    dup_amount = 250.00
    dup_vdate = rand_date(MAX_DATE, 15)
    dup_account = rng.choice(ACCOUNTS)
    ledger.append(
        {"trade_id": "DUP0001", "amount": dup_amount, "ccy": "USD",
         "value_date": dup_vdate.isoformat(), "account": dup_account,
         "counterparty": rng.choice(COUNTERPARTIES)}
    )
    for _ in range(2):
        statement.append(
            {"ref": "DUP0001", "amount": dup_amount, "ccy": "USD",
             "value_date": dup_vdate.isoformat(), "account": dup_account,
             "description": "Duplicate posting"}
        )

    # 6) Archetype #5: fee / charge difference (delta within 0.05 < x <= 5).
    # Fixed amounts for the same reason as the FX rounding rows above.
    for i, (amount, fee) in enumerate(((312.00, 2.00), (188.50, 3.50)), start=1):
        trade_id = f"FEE{i:04d}"
        vdate = rand_date(MAX_DATE, 15)
        account = rng.choice(ACCOUNTS)
        ledger.append(
            {"trade_id": trade_id, "amount": amount, "ccy": "USD",
             "value_date": vdate.isoformat(), "account": account,
             "counterparty": rng.choice(COUNTERPARTIES)}
        )
        statement.append(
            {"ref": trade_id, "amount": round(amount + fee, 2), "ccy": "USD",
             "value_date": vdate.isoformat(), "account": account,
             "description": "Includes service fee"}
        )

    # 7) Archetype #6: timing / settlement lag — ledger-only, dated within the
    #    last 2 days of the dataset (recent -> not yet posted on statement).
    for i in range(1, 3):
        ledger.append(
            {"trade_id": f"LAG{i:04d}", "amount": round(rng.uniform(100, 900), 2), "ccy": "USD",
             "value_date": (MAX_DATE - timedelta(days=i - 1)).isoformat(),
             "account": rng.choice(ACCOUNTS), "counterparty": rng.choice(COUNTERPARTIES)}
        )

    # 8) Archetype #7: wrong account/reference — everything matches except account.
    # Fixed amounts for the same reason as the FX rounding rows above.
    for i, amount in enumerate((410.00, 733.25), start=1):
        trade_id = f"WAC{i:04d}"
        vdate = rand_date(MAX_DATE, 15)
        accounts = rng.sample(ACCOUNTS, 2)
        ledger.append(
            {"trade_id": trade_id, "amount": amount, "ccy": "USD",
             "value_date": vdate.isoformat(), "account": accounts[0],
             "counterparty": rng.choice(COUNTERPARTIES)}
        )
        statement.append(
            {"ref": trade_id, "amount": amount, "ccy": "USD",
             "value_date": vdate.isoformat(), "account": accounts[1],
             "description": "Posted to alternate account"}
        )

    # 9) Archetype #8: missing counterparty leg — old, one-sided, on each side.
    ledger.append(
        {"trade_id": "OLD0001", "amount": round(rng.uniform(200, 900), 2), "ccy": "USD",
         "value_date": OLD_DATE.isoformat(), "account": rng.choice(ACCOUNTS),
         "counterparty": rng.choice(COUNTERPARTIES)}
    )
    statement.append(
        {"ref": "OLD0002", "amount": round(rng.uniform(200, 900), 2), "ccy": "USD",
         "value_date": OLD_DATE.isoformat(), "account": rng.choice(ACCOUNTS),
         "description": "Unmatched legacy posting"}
    )

    # 10) Archetype #9: amount outside tolerance — large, non-clean-fraction delta.
    # Fixed amounts, chosen so amount/(amount+137.42) is nowhere near a "nice
    # fraction" (which would misclassify this as partial_fill instead).
    for i, amount in enumerate((1618.00, 923.00), start=1):
        trade_id = f"TOL{i:04d}"
        vdate = rand_date(MAX_DATE, 15)
        account = rng.choice(ACCOUNTS)
        ledger.append(
            {"trade_id": trade_id, "amount": amount, "ccy": "USD",
             "value_date": vdate.isoformat(), "account": account,
             "counterparty": rng.choice(COUNTERPARTIES)}
        )
        statement.append(
            {"ref": trade_id, "amount": round(amount + 137.42, 2), "ccy": "USD",
             "value_date": vdate.isoformat(), "account": account,
             "description": "Amount discrepancy"}
        )

    # 11) Archetype #10: reference/ID format mismatch — same alnum, different
    #     punctuation/case; everything else matches so the merge is clean.
    # Fixed amounts for the same reason as the FX rounding rows above.
    for i, amount in enumerate((640.00, 275.50), start=1):
        vdate = rand_date(MAX_DATE, 15)
        account = rng.choice(ACCOUNTS)
        ledger.append(
            {"trade_id": f"FMT-{2000 + i}", "amount": amount, "ccy": "USD",
             "value_date": vdate.isoformat(), "account": account,
             "counterparty": rng.choice(COUNTERPARTIES)}
        )
        statement.append(
            {"ref": f"fmt{2000 + i}", "amount": amount, "ccy": "USD",
             "value_date": vdate.isoformat(), "account": account,
             "description": "Differently formatted reference"}
        )

    df_ledger = pd.DataFrame(ledger)
    df_statement = pd.DataFrame(statement)
    return df_ledger, df_statement, DEFAULT_CONFIG


def assert_all_archetypes_present(df_ledger: pd.DataFrame, df_statement: pd.DataFrame) -> None:
    result = reconcile(df_ledger, df_statement, DEFAULT_CONFIG)
    found = {b["archetype"] for b in result.breaks}
    missing = EXPECTED_ARCHETYPES - found
    if missing:
        raise AssertionError(
            f"Seed data is missing archetypes: {sorted(missing)}. Found: {sorted(found)}"
        )
    drift_breaks = [b for b in result.breaks if b["break_key"].startswith("DRF")]
    if len(drift_breaks) < 5:
        raise AssertionError(
            f"Expected the 3-day drift cluster to yield >=5 breaks, got {len(drift_breaks)}"
        )
    for b in drift_breaks:
        date_deltas = [v for k, v in b["deltas"].items() if "date_tolerance" in k]
        if date_deltas != [3]:
            raise AssertionError(f"Drift break {b['break_key']} does not show a 3-day delta: {b['deltas']}")


def write_seed(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    df_ledger, df_statement, config = generate()
    assert_all_archetypes_present(df_ledger, df_statement)

    df_ledger.to_csv(out_dir / "ledger.csv", index=False)
    df_statement.to_csv(out_dir / "statement.csv", index=False)
    (out_dir / "default_config.json").write_text(json.dumps(config, indent=2))
    print(f"Seed written to {out_dir}: {len(df_ledger)} ledger rows, {len(df_statement)} statement rows.")
    print("All 10 break archetypes + 3-day drift cluster verified present.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate ReconForge seed data.")
    parser.add_argument("--out", type=str, default="./data", help="Output directory")
    args = parser.parse_args()
    write_seed(Path(args.out))


if __name__ == "__main__":
    main()
