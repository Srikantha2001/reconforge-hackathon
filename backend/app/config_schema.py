"""The frozen config contract (§5) — JSON Schema, validation, repair-on-fail.

The LLM authors config; this module is the gate that decides whether that
config is well-formed enough to store and run. Near-misses are repaired
deterministically (never by the LLM) and re-validated; anything still invalid
hard-fails so a broken rule can never reach the engine.
"""
from __future__ import annotations

import copy
from typing import Any, Dict, List, Tuple

from jsonschema import Draft7Validator

# Engine capabilities — the contract deliberately implements exactly these.
MATCH_TYPES = ("exact", "numeric_tolerance", "date_tolerance")
TRANSFORM_OPS = ("abs", "upper", "lower", "strip", "round2")
TRANSFORM_SIDES = ("a", "b", "both")

CONFIG_SCHEMA: Dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "ReconForge config",
    "type": "object",
    "additionalProperties": False,
    "required": ["recon_name", "source_a", "source_b", "match_rules"],
    "properties": {
        "recon_name": {"type": "string", "minLength": 1},
        "source_a": {"$ref": "#/definitions/source"},
        "source_b": {"$ref": "#/definitions/source"},
        "transforms": {
            "type": "array",
            "items": {"$ref": "#/definitions/transform"},
            "default": [],
        },
        "match_rules": {
            "type": "array",
            "minItems": 1,
            "items": {"$ref": "#/definitions/match_rule"},
        },
    },
    "definitions": {
        "source": {
            "type": "object",
            "additionalProperties": False,
            "required": ["alias", "key_columns"],
            "properties": {
                "alias": {"type": "string", "minLength": 1},
                "key_columns": {
                    "type": "array",
                    "minItems": 1,
                    "items": {"type": "string", "minLength": 1},
                },
            },
        },
        "transform": {
            "type": "object",
            "additionalProperties": False,
            "required": ["field", "op"],
            "properties": {
                "field": {"type": "string", "minLength": 1},
                "op": {"type": "string", "enum": list(TRANSFORM_OPS)},
                "side": {"type": "string", "enum": list(TRANSFORM_SIDES)},
            },
        },
        "match_rule": {
            "type": "object",
            "additionalProperties": False,
            "required": ["field_a", "field_b", "type"],
            "properties": {
                "field_a": {"type": "string", "minLength": 1},
                "field_b": {"type": "string", "minLength": 1},
                "type": {"type": "string", "enum": list(MATCH_TYPES)},
                "tolerance": {"type": "number"},
                "tolerance_days": {"type": "integer", "minimum": 0},
            },
            "allOf": [
                {
                    "if": {"properties": {"type": {"const": "numeric_tolerance"}}},
                    "then": {"required": ["tolerance"]},
                },
                {
                    "if": {"properties": {"type": {"const": "date_tolerance"}}},
                    "then": {"required": ["tolerance_days"]},
                },
            ],
        },
    },
}

_VALIDATOR = Draft7Validator(CONFIG_SCHEMA)

# camelCase / common-alias -> canonical snake_case key names.
_KEY_ALIASES = {
    "reconname": "recon_name",
    "sourcea": "source_a",
    "sourceb": "source_b",
    "keycolumns": "key_columns",
    "matchrules": "match_rules",
    "fielda": "field_a",
    "fieldb": "field_b",
    "tolerancedays": "tolerance_days",
    "tolerance_day": "tolerance_days",
}

# Free-text match-type synonyms the LLM might emit.
_TYPE_ALIASES = {
    "numeric": "numeric_tolerance",
    "number": "numeric_tolerance",
    "amount": "numeric_tolerance",
    "date": "date_tolerance",
    "exact_match": "exact",
    "equals": "exact",
}


class ConfigValidationError(ValueError):
    """Raised when config is invalid even after repair."""

    def __init__(self, errors: List[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


def _canonical_key(key: str) -> str:
    collapsed = key.replace("-", "").replace("_", "").lower()
    return _KEY_ALIASES.get(collapsed, key)


def _normalize_keys(obj: Any) -> Any:
    """Recursively rename camelCase/alias keys to their canonical form."""
    if isinstance(obj, dict):
        return {_canonical_key(k): _normalize_keys(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_normalize_keys(v) for v in obj]
    return obj


def _coerce_number(value: Any) -> Any:
    if isinstance(value, str):
        s = value.strip()
        try:
            if "." in s or "e" in s.lower():
                return float(s)
            return int(s)
        except ValueError:
            return value
    return value


def repair(raw: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """Best-effort deterministic repair of near-miss config.

    Returns the repaired config and a list of human-readable repairs applied.
    """
    repairs: List[str] = []
    cfg = _normalize_keys(copy.deepcopy(raw))
    if cfg != _normalize_keys(raw):  # pragma: no cover - defensive
        pass

    # Detect key renames for the audit trail (compare shallow top-level keys).
    if set(raw.keys()) != set(cfg.keys()):
        repairs.append("normalized camelCase/alias keys to snake_case")

    for rule in cfg.get("match_rules", []) or []:
        if not isinstance(rule, dict):
            continue
        # Type synonyms.
        rtype = rule.get("type")
        if isinstance(rtype, str) and rtype not in MATCH_TYPES:
            mapped = _TYPE_ALIASES.get(rtype.strip().lower())
            if mapped:
                rule["type"] = mapped
                repairs.append(f"mapped match type '{rtype}' -> '{mapped}'")

        # Stringified numerics.
        for numeric_field in ("tolerance", "tolerance_days"):
            if numeric_field in rule and isinstance(rule[numeric_field], str):
                coerced = _coerce_number(rule[numeric_field])
                if coerced != rule[numeric_field]:
                    rule[numeric_field] = coerced
                    repairs.append(f"coerced string {numeric_field} -> number")

        # tolerance-on-date-rule: a date rule carrying `tolerance` should use
        # `tolerance_days`.
        if rule.get("type") == "date_tolerance" and "tolerance" in rule:
            if "tolerance_days" not in rule:
                rule["tolerance_days"] = int(round(_coerce_number(rule.pop("tolerance"))))
                repairs.append("moved 'tolerance' to 'tolerance_days' on date rule")
            else:
                rule.pop("tolerance", None)
                repairs.append("dropped stray 'tolerance' on date rule")

        # tolerance_days must be an int.
        if "tolerance_days" in rule and isinstance(rule["tolerance_days"], float):
            rule["tolerance_days"] = int(round(rule["tolerance_days"]))
            repairs.append("rounded tolerance_days to integer")

    # Default empty transforms list.
    if "transforms" not in cfg:
        cfg["transforms"] = []

    return cfg, repairs


def validate(config: Dict[str, Any]) -> List[str]:
    """Return a list of schema error strings (empty when valid)."""
    errors = sorted(_VALIDATOR.iter_errors(config), key=lambda e: list(e.path))
    return [f"{'/'.join(str(p) for p in e.path) or '<root>'}: {e.message}" for e in errors]


def validate_and_repair(raw: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """Validate; on failure repair once and re-validate.

    Returns (valid_config, repairs_applied). Raises ConfigValidationError if the
    config is still invalid after repair.
    """
    errors = validate(raw)
    if not errors:
        return raw, []

    repaired, repairs = repair(raw)
    errors_after = validate(repaired)
    if errors_after:
        raise ConfigValidationError(errors_after)
    return repaired, repairs
