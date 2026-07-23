"""ReconOS config schema v2: validation + deterministic repair-on-fail.

The canonical valid config is the seed generator's DEFAULT_CONFIG (recon_001).
(docs/RECONOS_UPGRADE_PLAN.md §4 P2 acceptance criteria.)
"""
import copy

import pytest

from app.config_schema import (
    ConfigValidationError,
    repair,
    validate,
    validate_and_repair,
)
from app.seed.generator import DEFAULT_CONFIG


def test_seed_default_config_is_valid():
    assert validate(DEFAULT_CONFIG) == []


def test_valid_config_passes_through_untouched():
    cfg, repairs = validate_and_repair(DEFAULT_CONFIG)
    assert cfg == DEFAULT_CONFIG
    assert repairs == []


def test_all_seven_waterfall_pass_types_accepted():
    types = [p["type"] for p in DEFAULT_CONFIG["matching_waterfall"]]
    assert types == [
        "ONE_TO_ONE", "ONE_TO_ONE", "ONE_TO_ONE", "ONE_TO_ONE",
        "ONE_TO_MANY", "MANY_TO_ONE", "N_TO_M_SUBSET_SUM",
    ]
    assert validate(DEFAULT_CONFIG) == []


def test_missing_required_root_field_fails():
    for field in ("recon_id", "recon_type", "version", "matching_waterfall", "output_hash_spec"):
        bad = {k: v for k, v in DEFAULT_CONFIG.items() if k != field}
        assert validate(bad) != [], f"missing {field} should be an error"


def test_bad_recon_type_rejected():
    bad = copy.deepcopy(DEFAULT_CONFIG)
    bad["recon_type"] = "NOT_A_REAL_TYPE"
    assert validate(bad) != []


def test_non_semver_version_rejected():
    bad = copy.deepcopy(DEFAULT_CONFIG)
    bad["version"] = "v1"
    assert validate(bad) != []


def test_bad_status_rejected():
    bad = copy.deepcopy(DEFAULT_CONFIG)
    bad["status"] = "LIVE"
    assert validate(bad) != []


def test_unknown_additional_property_rejected():
    bad = copy.deepcopy(DEFAULT_CONFIG)
    bad["unexpected_field"] = "nope"
    assert validate(bad) != []


def test_numeric_tolerance_rule_without_tolerance_fails_hard():
    bad = copy.deepcopy(DEFAULT_CONFIG)
    bad["matching_waterfall"][2]["value_rules"] = [
        {"field_a": "quantity", "field_b": "quantity", "match_type": "NUMERIC_TOLERANCE"}
    ]
    with pytest.raises(ConfigValidationError):
        validate_and_repair(bad)


def test_date_tolerance_rule_without_days_fails_hard():
    bad = copy.deepcopy(DEFAULT_CONFIG)
    bad["matching_waterfall"][1]["value_rules"] = [
        {"field_a": "settlement_date", "field_b": "posting_date", "match_type": "DATE_TOLERANCE"}
    ]
    with pytest.raises(ConfigValidationError):
        validate_and_repair(bad)


def test_asymmetric_tolerance_requires_min_and_max():
    bad = copy.deepcopy(DEFAULT_CONFIG)
    bad["matching_waterfall"][0]["value_rules"] = [
        {"field_a": "quantity", "field_b": "quantity", "match_type": "ASYMMETRIC_TOLERANCE"}
    ]
    with pytest.raises(ConfigValidationError):
        validate_and_repair(bad)


# --- Repair-on-fail (deterministic) ----------------------------------------

def test_repair_camelcase_keys():
    raw = copy.deepcopy(DEFAULT_CONFIG)
    raw["reconType"] = raw.pop("recon_type")
    raw["sourceTopology"] = raw.pop("source_topology")
    raw["matchingWaterfall"] = raw.pop("matching_waterfall")
    for p in raw["matchingWaterfall"]:
        if "value_rules" in p:
            for rule in p["value_rules"]:
                if "match_type" in rule:
                    rule["matchType"] = rule.pop("match_type")
                if "field_a" in rule:
                    rule["fieldA"] = rule.pop("field_a")
                if "field_b" in rule:
                    rule["fieldB"] = rule.pop("field_b")
    cfg, repairs = validate_and_repair(raw)
    assert cfg["recon_type"] == "POSITION"
    assert cfg["source_topology"] == "ONE_VS_ONE"
    assert repairs


def test_repair_semver_from_int_and_short_string():
    raw = copy.deepcopy(DEFAULT_CONFIG)
    raw["version"] = 2
    cfg, repairs = validate_and_repair(raw)
    assert cfg["version"] == "2.0.0"

    raw2 = copy.deepcopy(DEFAULT_CONFIG)
    raw2["version"] = "1.2"
    cfg2, _ = validate_and_repair(raw2)
    assert cfg2["version"] == "1.2.0"


def test_repair_match_type_synonym():
    raw = copy.deepcopy(DEFAULT_CONFIG)
    raw["matching_waterfall"][2]["value_rules"][0]["match_type"] = "numeric"
    cfg, repairs = validate_and_repair(raw)
    assert cfg["matching_waterfall"][2]["value_rules"][0]["match_type"] == "NUMERIC_TOLERANCE"


def test_repair_stringified_tolerance():
    raw = copy.deepcopy(DEFAULT_CONFIG)
    raw["matching_waterfall"][2]["value_rules"][0]["tolerance"] = "1.0"
    cfg, repairs = validate_and_repair(raw)
    tol = cfg["matching_waterfall"][2]["value_rules"][0]["tolerance"]
    assert tol == 1.0 and isinstance(tol, float)


def test_repair_tolerance_on_date_rule():
    raw = copy.deepcopy(DEFAULT_CONFIG)
    # A DATE_TOLERANCE rule mistakenly carrying `tolerance` instead of days.
    raw["matching_waterfall"][1]["value_rules"][1] = {
        "field_a": "settlement_date", "field_b": "posting_date",
        "match_type": "DATE_TOLERANCE", "tolerance": 2,
    }
    cfg, repairs = validate_and_repair(raw)
    rule = cfg["matching_waterfall"][1]["value_rules"][1]
    assert rule["tolerance_days"] == 2 and "tolerance" not in rule


def test_repair_injects_default_governance_blocks():
    raw = copy.deepcopy(DEFAULT_CONFIG)
    del raw["autonomy_config"]
    del raw["output_hash_spec"]
    cfg, repairs = validate_and_repair(raw)
    assert cfg["autonomy_config"]["stp_confidence_threshold"] == 0.90
    assert cfg["output_hash_spec"]["hash_algorithm"] == "SHA256"
    assert any("autonomy_config" in r for r in repairs)


def test_repair_defaults_status_to_draft():
    raw = copy.deepcopy(DEFAULT_CONFIG)
    del raw["status"]
    cfg, repairs = validate_and_repair(raw)
    assert cfg["status"] == "DRAFT"


def test_repair_assigns_missing_pass_numbers():
    raw = copy.deepcopy(DEFAULT_CONFIG)
    for p in raw["matching_waterfall"]:
        p.pop("pass", None)
    repaired, repairs = repair(raw)
    assert [p["pass"] for p in repaired["matching_waterfall"]] == [1, 2, 3, 4, 5, 6, 7]


def test_superseded_status_is_valid():
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    cfg["status"] = "SUPERSEDED"
    assert validate(cfg) == []


def test_still_invalid_after_repair_hard_fails():
    # A config too broken to repair (unknown pass type can't be defaulted).
    raw = copy.deepcopy(DEFAULT_CONFIG)
    raw["matching_waterfall"][0]["type"] = "TELEPATHIC_MATCH"
    with pytest.raises(ConfigValidationError):
        validate_and_repair(raw)
