"""Frozen config schema: validation + deterministic repair-on-fail."""
import pytest

from app.config_schema import ConfigValidationError, validate, validate_and_repair

VALID_CONFIG = {
    "recon_name": "Nostro_USD_Daily",
    "source_a": {"alias": "ledger", "key_columns": ["trade_id"]},
    "source_b": {"alias": "statement", "key_columns": ["ref"]},
    "transforms": [{"field": "amount", "op": "abs"}, {"field": "ccy", "op": "upper"}],
    "match_rules": [
        {"field_a": "trade_id", "field_b": "ref", "type": "exact"},
        {"field_a": "amount", "field_b": "amount", "type": "numeric_tolerance", "tolerance": 0.01},
        {"field_a": "value_date", "field_b": "value_date", "type": "date_tolerance", "tolerance_days": 2},
    ],
}


def test_valid_config_has_no_errors():
    assert validate(VALID_CONFIG) == []


def test_valid_config_passes_through_untouched():
    cfg, repairs = validate_and_repair(VALID_CONFIG)
    assert cfg == VALID_CONFIG
    assert repairs == []


def test_missing_required_field_fails():
    bad = {k: v for k, v in VALID_CONFIG.items() if k != "match_rules"}
    assert validate(bad) != []
    with pytest.raises(ConfigValidationError):
        validate_and_repair(bad)


def test_numeric_tolerance_without_tolerance_field_fails_hard():
    bad = {
        **VALID_CONFIG,
        "match_rules": [{"field_a": "amount", "field_b": "amount", "type": "numeric_tolerance"}],
    }
    with pytest.raises(ConfigValidationError):
        validate_and_repair(bad)


def test_repair_camelcase_keys():
    raw = {
        "reconName": "Test",
        "sourceA": {"alias": "ledger", "keyColumns": ["trade_id"]},
        "sourceB": {"alias": "statement", "keyColumns": ["ref"]},
        "matchRules": [{"fieldA": "trade_id", "fieldB": "ref", "type": "exact"}],
    }
    cfg, repairs = validate_and_repair(raw)
    assert cfg["recon_name"] == "Test"
    assert cfg["source_a"]["key_columns"] == ["trade_id"]
    assert cfg["match_rules"][0]["field_a"] == "trade_id"
    assert repairs  # something was repaired


def test_repair_stringified_tolerance():
    raw = {
        **VALID_CONFIG,
        "match_rules": [
            {"field_a": "amount", "field_b": "amount", "type": "numeric_tolerance", "tolerance": "0.05"}
        ],
    }
    cfg, repairs = validate_and_repair(raw)
    assert cfg["match_rules"][0]["tolerance"] == 0.05
    assert isinstance(cfg["match_rules"][0]["tolerance"], float)


def test_repair_tolerance_on_date_rule():
    raw = {
        **VALID_CONFIG,
        "match_rules": [
            {"field_a": "value_date", "field_b": "value_date", "type": "date_tolerance", "tolerance": 2}
        ],
    }
    cfg, repairs = validate_and_repair(raw)
    rule = cfg["match_rules"][0]
    assert rule["tolerance_days"] == 2
    assert "tolerance" not in rule


def test_repair_match_type_synonym():
    raw = {
        **VALID_CONFIG,
        "match_rules": [{"field_a": "amount", "field_b": "amount", "type": "amount", "tolerance": 0.01}],
    }
    cfg, repairs = validate_and_repair(raw)
    assert cfg["match_rules"][0]["type"] == "numeric_tolerance"


def test_still_invalid_after_repair_hard_fails():
    raw = {"recon_name": "X", "source_a": {}, "source_b": {}, "match_rules": []}
    with pytest.raises(ConfigValidationError):
        validate_and_repair(raw)


def test_unknown_additional_properties_rejected():
    bad = {**VALID_CONFIG, "unexpected_field": "nope"}
    assert validate(bad) != []
