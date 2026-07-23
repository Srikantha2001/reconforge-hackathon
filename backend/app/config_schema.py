"""The v2 (ReconOS) config contract — JSON Schema, validation, repair-on-fail.

The LLM authors config; this module is the gate that decides whether that
config is well-formed enough to store and run. Near-misses are repaired
deterministically (never by the LLM) and re-validated; anything still invalid
hard-fails so a broken rule can never reach the engine.

v2 (P2, docs/RECONOS_UPGRADE_PLAN.md): full ReconOS contract — recon typing,
semver versions, source topology, auxiliary files, per-side transforms,
position control, a 7-pass matching waterfall, regulatory and autonomy blocks,
and the output-hash spec. The canonical example is
``app.seed.generator.DEFAULT_CONFIG``.
"""
from __future__ import annotations

import copy
import re
from typing import Any, Dict, List, Tuple

from jsonschema import Draft7Validator

# --- Engine capabilities: the contract implements exactly these -------------
RECON_TYPES = (
    "POSITION", "TRADE", "CASH", "CORPORATE_ACTION", "COLLATERAL", "NAV",
    "CASS", "FAILS", "FX", "SEC_LENDING", "REPO", "GL_SUBSTANTIATION",
)
SOURCE_TOPOLOGIES = (
    "ONE_VS_ONE", "ONE_VS_MANY", "MANY_VS_ONE", "MANY_VS_MANY", "THREE_WAY", "FOUR_WAY",
)
CONFIG_STATUSES = ("DRAFT", "PENDING_APPROVAL", "APPROVED", "SUPERSEDED")
MATCH_TYPES = (
    "EXACT", "NUMERIC_TOLERANCE", "ASYMMETRIC_TOLERANCE", "DATE_TOLERANCE", "CASS_SHORTFALL",
)
PASS_TYPES = (
    "ONE_TO_ONE", "ONE_TO_MANY", "MANY_TO_ONE", "N_TO_M_SUBSET_SUM", "CASS_SPECIFIC",
)
TRANSFORM_OPS = (
    "sign_flip", "abs_value", "upper_case", "lower_case", "strip", "round2",
    "strip_leading_zeros", "date_normalise", "compute_market_value",
    "enrich_from_aux", "corporate_action_adjust",
)
SEMVER_PATTERN = r"^\d+\.\d+\.\d+$"

# Deterministic defaults injected by repair() when a block is missing.
DEFAULT_AUTONOMY_CONFIG: Dict[str, Any] = {
    "stp_confidence_threshold": 0.90,
    "write_off_auto_approve_below_eur": 500.00,
    "write_off_dual_checker_above_eur": 10000.00,
    "maker_checker_same_person_allowed": False,
    "pending_approval_expiry_hours": 24,
}
DEFAULT_OUTPUT_HASH_SPEC: Dict[str, Any] = {
    "hash_algorithm": "SHA256",
    "amount_format": "2_decimal_string",
    "quantity_format": "6_decimal_string",
    "date_format": "%Y-%m-%d",
}

_KEY_RULE = {
    "type": "object",
    "additionalProperties": False,
    "required": ["field_a", "field_b", "match_type"],
    "properties": {
        "field_a": {"type": "string", "minLength": 1},
        "field_b": {"type": "string", "minLength": 1},
        "match_type": {"type": "string", "enum": list(MATCH_TYPES)},
    },
}

_VALUE_RULE = {
    "type": "object",
    "additionalProperties": False,
    "required": ["field_a", "field_b", "match_type"],
    "properties": {
        "field_a": {"type": "string", "minLength": 1},
        "field_b": {"type": "string", "minLength": 1},
        "match_type": {"type": "string", "enum": list(MATCH_TYPES)},
        "tolerance": {"type": "number"},
        "min_variance": {"type": "number"},
        "max_variance": {"type": "number"},
        "tolerance_days": {"type": "integer", "minimum": 0},
        "business_days_only": {"type": "boolean"},
        "calendar_market": {"type": "string"},
        "tolerance_type": {"type": "string", "enum": ["ABSOLUTE", "RELATIVE"]},
    },
    "allOf": [
        {
            "if": {"properties": {"match_type": {"const": "NUMERIC_TOLERANCE"}}},
            "then": {"required": ["tolerance"]},
        },
        {
            "if": {"properties": {"match_type": {"const": "DATE_TOLERANCE"}}},
            "then": {"required": ["tolerance_days"]},
        },
        {
            "if": {"properties": {"match_type": {"const": "ASYMMETRIC_TOLERANCE"}}},
            "then": {"required": ["min_variance", "max_variance"]},
        },
    ],
}

_TRANSFORM = {
    "type": "object",
    "additionalProperties": False,
    "required": ["step", "op"],
    "properties": {
        "step": {"type": "integer", "minimum": 1},
        "op": {"type": "string", "enum": list(TRANSFORM_OPS)},
        "column": {"type": "string"},
        "condition": {"type": "string"},
        "max_length": {"type": "integer", "minimum": 1},
        "input_format": {"type": "string"},
        "factor": {"type": "number"},
        "separator": {"type": "string"},
        "output_col": {"type": "string"},
        "columns": {"type": "array", "items": {"type": "string"}},
        "quantity_col": {"type": "string"},
        "price_col": {"type": "string"},
        "aux_alias": {"type": "string"},
        "join_column": {"type": "string"},
        "add_columns": {"type": "array", "items": {"type": "string"}},
    },
}

_POSITION_SIDE = {
    "type": "object",
    "additionalProperties": False,
    "required": ["balance_type"],
    "properties": {
        "opening_balance_field": {"type": ["string", "null"]},
        "closing_balance_field": {"type": ["string", "null"]},
        "movement_field": {"type": ["string", "null"]},
        "balance_type": {"type": "string", "enum": ["AMOUNT", "QUANTITY"]},
    },
}

_MATCH_PASS = {
    "type": "object",
    "additionalProperties": False,
    "required": ["pass", "name", "type"],
    "properties": {
        "pass": {"type": "integer", "minimum": 1},
        "name": {"type": "string", "minLength": 1},
        "type": {"type": "string", "enum": list(PASS_TYPES)},
        "key_rules": {"type": "array", "items": _KEY_RULE},
        "value_rules": {"type": "array", "items": _VALUE_RULE},
        "group_by_a": {"type": "array", "items": {"type": "string"}},
        "group_by_b": {"type": "array", "items": {"type": "string"}},
        "aggregate_field_a": {"type": "string"},
        "aggregate_field_b": {"type": "string"},
        "aggregate_op": {"type": "string", "enum": ["SUM"]},
        "value_field_a": {"type": "string"},
        "value_field_b": {"type": "string"},
        "partition_col": {"type": "string"},
        "tolerance": {"type": "number"},
        # Optional per-pass ISIN scope: the pass only operates on rows whose
        # isin is in this list (others stay in the pool for later passes).
        # Used to keep the aggregate passes (5/6/7) from claiming each other's
        # fixtures. (docs/RECONOS_UPGRADE_PLAN.md §4 P3 — user decision.)
        "restrict_isins": {"type": "array", "items": {"type": "string"}},
        "performance_guard": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "max_group_size": {"type": "integer", "minimum": 1},
                "max_rows_per_partition": {"type": "integer", "minimum": 1},
                "timeout_seconds": {"type": "integer", "minimum": 1},
            },
        },
    },
    "allOf": [
        {
            "if": {"properties": {"type": {"const": "ONE_TO_ONE"}}},
            "then": {"required": ["key_rules", "value_rules"]},
        },
        {
            "if": {"properties": {"type": {"const": "ONE_TO_MANY"}}},
            "then": {"required": ["key_rules", "group_by_b", "aggregate_field_b", "aggregate_op", "value_rules"]},
        },
        {
            "if": {"properties": {"type": {"const": "MANY_TO_ONE"}}},
            "then": {"required": ["key_rules", "group_by_a", "aggregate_field_a", "aggregate_op", "value_rules"]},
        },
        {
            "if": {"properties": {"type": {"const": "N_TO_M_SUBSET_SUM"}}},
            "then": {"required": ["value_field_a", "value_field_b", "partition_col", "tolerance"]},
        },
    ],
}

CONFIG_SCHEMA: Dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "ReconOS config v2",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "recon_id", "recon_name", "recon_type", "version", "status",
        "source_topology", "sources", "transforms", "position_control",
        "matching_waterfall", "autonomy_config", "output_hash_spec",
    ],
    "properties": {
        "recon_id": {"type": "string", "minLength": 1},
        "recon_name": {"type": "string", "minLength": 1},
        "recon_type": {"type": "string", "enum": list(RECON_TYPES)},
        "version": {"type": "string", "pattern": SEMVER_PATTERN},
        "status": {"type": "string", "enum": list(CONFIG_STATUSES)},
        "source_topology": {"type": "string", "enum": list(SOURCE_TOPOLOGIES)},
        "sources": {
            "type": "array",
            "minItems": 2,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "alias", "side", "file"],
                "properties": {
                    "id": {"type": "string", "minLength": 1},
                    "alias": {"type": "string", "minLength": 1},
                    "side": {"type": "string", "enum": ["A", "B", "C", "D"]},
                    "file": {"type": "string", "minLength": 1},
                    "ingestion_type": {"type": "string"},
                    "consolidation_key": {"type": ["string", "null"]},
                    "matching_unit": {"type": "string", "enum": ["AMOUNT", "QUANTITY"]},
                    "sign_convention": {"type": "string"},
                    "auto_populated_by_bank": {"type": "boolean"},
                },
            },
        },
        "auxiliary_files": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "alias", "file", "key_column"],
                "properties": {
                    "id": {"type": "string", "minLength": 1},
                    "alias": {"type": "string", "minLength": 1},
                    "file": {"type": "string", "minLength": 1},
                    "key_column": {"type": "string", "minLength": 1},
                    "value_column": {"type": ["string", "null"]},
                },
            },
        },
        "transforms": {
            "type": "object",
            "additionalProperties": False,
            "required": ["side_a", "side_b"],
            "properties": {
                "side_a": {"type": "array", "items": _TRANSFORM},
                "side_b": {"type": "array", "items": _TRANSFORM},
            },
        },
        "position_control": {
            "type": "object",
            "additionalProperties": False,
            "required": ["enabled", "side_a", "side_b", "tolerance", "explained_break_categories"],
            "properties": {
                "enabled": {"type": "boolean"},
                "side_a": _POSITION_SIDE,
                "side_b": _POSITION_SIDE,
                "tolerance": {"type": "number", "minimum": 0},
                "explained_break_categories": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["CORPORATE_ACTION", "PENDING_SETTLEMENT"]},
                },
            },
        },
        "matching_waterfall": {"type": "array", "minItems": 1, "items": _MATCH_PASS},
        "regulatory_config": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "emir": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["enabled", "dispute_amount_threshold_eur", "dispute_days_threshold"],
                    "properties": {
                        "enabled": {"type": "boolean"},
                        "dispute_amount_threshold_eur": {"type": "number", "minimum": 0},
                        "dispute_days_threshold": {"type": "integer", "minimum": 0},
                        "auto_generate_notification": {"type": "boolean"},
                        "competent_authority": {"type": "string"},
                    },
                },
                "cass": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["enabled", "regime"],
                    "properties": {
                        "enabled": {"type": "boolean"},
                        "regime": {"type": "string", "enum": ["CASS_7A"]},
                        "reconciliation_frequency": {"type": "string", "enum": ["DAILY", "MONTHLY"]},
                        "shortfall_escalation_threshold_eur": {"type": "number", "minimum": 0},
                    },
                },
            },
        },
        "autonomy_config": {
            "type": "object",
            "additionalProperties": False,
            "required": ["stp_confidence_threshold"],
            "properties": {
                "stp_confidence_threshold": {"type": "number", "minimum": 0, "maximum": 1},
                "write_off_auto_approve_below_eur": {"type": "number", "minimum": 0},
                "write_off_dual_checker_above_eur": {"type": "number", "minimum": 0},
                "maker_checker_same_person_allowed": {"type": "boolean"},
                "pending_approval_expiry_hours": {"type": "integer", "minimum": 1},
            },
        },
        "output_hash_spec": {
            "type": "object",
            "additionalProperties": False,
            "required": ["hash_algorithm"],
            "properties": {
                "hash_algorithm": {"type": "string", "enum": ["SHA256"]},
                "amount_format": {"type": "string"},
                "quantity_format": {"type": "string"},
                "date_format": {"type": "string"},
            },
        },
    },
}

_VALIDATOR = Draft7Validator(CONFIG_SCHEMA)

# camelCase / common-alias -> canonical snake_case key names, matched on the
# key with '-'/'_' stripped and lowercased.
_KEY_ALIASES = {
    "reconid": "recon_id",
    "reconname": "recon_name",
    "recontype": "recon_type",
    "sourcetopology": "source_topology",
    "auxiliaryfiles": "auxiliary_files",
    "sidea": "side_a",
    "sideb": "side_b",
    "positioncontrol": "position_control",
    "matchingwaterfall": "matching_waterfall",
    "regulatoryconfig": "regulatory_config",
    "autonomyconfig": "autonomy_config",
    "outputhashspec": "output_hash_spec",
    "keyrules": "key_rules",
    "valuerules": "value_rules",
    "fielda": "field_a",
    "fieldb": "field_b",
    "matchtype": "match_type",
    "tolerancedays": "tolerance_days",
    "tolerance_day": "tolerance_days",
    "minvariance": "min_variance",
    "maxvariance": "max_variance",
    "businessdaysonly": "business_days_only",
    "calendarmarket": "calendar_market",
    "tolerancetype": "tolerance_type",
    "groupbya": "group_by_a",
    "groupbyb": "group_by_b",
    "aggregatefielda": "aggregate_field_a",
    "aggregatefieldb": "aggregate_field_b",
    "aggregateop": "aggregate_op",
    "valuefielda": "value_field_a",
    "valuefieldb": "value_field_b",
    "partitioncol": "partition_col",
    "performanceguard": "performance_guard",
    "maxgroupsize": "max_group_size",
    "maxrowsperpartition": "max_rows_per_partition",
    "timeoutseconds": "timeout_seconds",
    "openingbalancefield": "opening_balance_field",
    "closingbalancefield": "closing_balance_field",
    "movementfield": "movement_field",
    "balancetype": "balance_type",
    "explainedbreakcategories": "explained_break_categories",
    "stpconfidencethreshold": "stp_confidence_threshold",
    "writeoffautoapprovebeloweur": "write_off_auto_approve_below_eur",
    "writeoffdualcheckeraboveeur": "write_off_dual_checker_above_eur",
    "makercheckersamepersonallowed": "maker_checker_same_person_allowed",
    "pendingapprovalexpiryhours": "pending_approval_expiry_hours",
    "disputeamountthresholdeur": "dispute_amount_threshold_eur",
    "disputedaysthreshold": "dispute_days_threshold",
    "autogeneratenotification": "auto_generate_notification",
    "competentauthority": "competent_authority",
    "reconciliationfrequency": "reconciliation_frequency",
    "shortfallescalationthresholdeur": "shortfall_escalation_threshold_eur",
    "hashalgorithm": "hash_algorithm",
    "amountformat": "amount_format",
    "quantityformat": "quantity_format",
    "dateformat": "date_format",
    "ingestiontype": "ingestion_type",
    "consolidationkey": "consolidation_key",
    "matchingunit": "matching_unit",
    "signconvention": "sign_convention",
    "autopopulatedbybank": "auto_populated_by_bank",
    "keycolumn": "key_column",
    "valuecolumn": "value_column",
    "inputformat": "input_format",
    "outputcol": "output_col",
    "quantitycol": "quantity_col",
    "pricecol": "price_col",
    "auxalias": "aux_alias",
    "joincolumn": "join_column",
    "addcolumns": "add_columns",
    "maxlength": "max_length",
    "passnumber": "pass",
}

# Free-text match-type synonyms the LLM might emit (lowercased key).
_MATCH_TYPE_ALIASES = {
    "exact": "EXACT",
    "exact_match": "EXACT",
    "equals": "EXACT",
    "numeric_tolerance": "NUMERIC_TOLERANCE",
    "numeric": "NUMERIC_TOLERANCE",
    "number": "NUMERIC_TOLERANCE",
    "amount": "NUMERIC_TOLERANCE",
    "asymmetric_tolerance": "ASYMMETRIC_TOLERANCE",
    "asymmetric": "ASYMMETRIC_TOLERANCE",
    "date_tolerance": "DATE_TOLERANCE",
    "date": "DATE_TOLERANCE",
    "cass_shortfall": "CASS_SHORTFALL",
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


def _semverize(value: Any) -> Any:
    """Deterministically coerce common version forms to semver strings."""
    if isinstance(value, int):
        return f"{value}.0.0"
    if isinstance(value, float):
        major = int(value)
        minor = int(round((value - major) * 10))
        return f"{major}.{minor}.0"
    if isinstance(value, str):
        s = value.strip().lstrip("v")
        if re.fullmatch(r"\d+", s):
            return f"{s}.0.0"
        if re.fullmatch(r"\d+\.\d+", s):
            return f"{s}.0"
        if re.fullmatch(SEMVER_PATTERN, s):
            return s
    return value


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _repair_rule(rule: Dict[str, Any], repairs: List[str]) -> None:
    """In-place repairs shared by key_rules and value_rules."""
    mtype = rule.get("match_type")
    if isinstance(mtype, str) and mtype not in MATCH_TYPES:
        mapped = _MATCH_TYPE_ALIASES.get(mtype.strip().lower())
        if mapped:
            rule["match_type"] = mapped
            repairs.append(f"mapped match type '{mtype}' -> '{mapped}'")

    for numeric_field in ("tolerance", "tolerance_days", "min_variance", "max_variance"):
        if numeric_field in rule and isinstance(rule[numeric_field], str):
            coerced = _coerce_number(rule[numeric_field])
            if coerced != rule[numeric_field]:
                rule[numeric_field] = coerced
                repairs.append(f"coerced string {numeric_field} -> number")

    if rule.get("match_type") == "DATE_TOLERANCE" and "tolerance" in rule:
        if "tolerance_days" not in rule:
            rule["tolerance_days"] = int(round(_coerce_number(rule.pop("tolerance"))))
            repairs.append("moved 'tolerance' to 'tolerance_days' on date rule")
        else:
            rule.pop("tolerance", None)
            repairs.append("dropped stray 'tolerance' on date rule")

    if "tolerance_days" in rule and isinstance(rule["tolerance_days"], float):
        rule["tolerance_days"] = int(round(rule["tolerance_days"]))
        repairs.append("rounded tolerance_days to integer")


def repair(raw: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """Best-effort deterministic repair of near-miss v2 config.

    Returns the repaired config and a list of human-readable repairs applied.
    Never consults an LLM.
    """
    repairs: List[str] = []
    cfg = _normalize_keys(copy.deepcopy(raw))
    if set(raw.keys()) != set(cfg.keys()):
        repairs.append("normalized camelCase/alias keys to snake_case")

    # Root-level scalar repairs.
    if "recon_id" not in cfg and isinstance(cfg.get("recon_name"), str):
        cfg["recon_id"] = f"recon_{_slug(cfg['recon_name'])}"
        repairs.append("derived recon_id from recon_name")

    if isinstance(cfg.get("recon_type"), str) and cfg["recon_type"] not in RECON_TYPES:
        upper = cfg["recon_type"].strip().upper()
        if upper in RECON_TYPES:
            cfg["recon_type"] = upper
            repairs.append("upper-cased recon_type")

    if "version" not in cfg:
        cfg["version"] = "1.0.0"
        repairs.append("defaulted version to 1.0.0")
    else:
        coerced = _semverize(cfg["version"])
        if coerced != cfg["version"]:
            cfg["version"] = coerced
            repairs.append("coerced version to semver")

    if "status" not in cfg:
        cfg["status"] = "DRAFT"
        repairs.append("defaulted status to DRAFT")
    elif isinstance(cfg["status"], str) and cfg["status"] not in CONFIG_STATUSES:
        upper = cfg["status"].strip().upper()
        if upper in CONFIG_STATUSES:
            cfg["status"] = upper
            repairs.append("upper-cased status")

    if isinstance(cfg.get("source_topology"), str) and cfg["source_topology"] not in SOURCE_TOPOLOGIES:
        upper = cfg["source_topology"].strip().upper()
        if upper in SOURCE_TOPOLOGIES:
            cfg["source_topology"] = upper
            repairs.append("upper-cased source_topology")

    # Transforms: default missing block/sides.
    if "transforms" not in cfg:
        cfg["transforms"] = {"side_a": [], "side_b": []}
        repairs.append("defaulted empty transforms")
    elif isinstance(cfg["transforms"], dict):
        for side in ("side_a", "side_b"):
            if side not in cfg["transforms"]:
                cfg["transforms"][side] = []
                repairs.append(f"defaulted empty transforms.{side}")

    # Waterfall repairs: pass numbering + rule-level fixes.
    passes = cfg.get("matching_waterfall")
    if isinstance(passes, list):
        for i, p in enumerate(passes):
            if not isinstance(p, dict):
                continue
            if "pass" not in p:
                p["pass"] = i + 1
                repairs.append(f"assigned sequential pass number {i + 1}")
            if isinstance(p.get("type"), str) and p["type"] not in PASS_TYPES:
                upper = p["type"].strip().upper()
                if upper in PASS_TYPES:
                    p["type"] = upper
                    repairs.append("upper-cased pass type")
            for rule_list in ("key_rules", "value_rules"):
                for rule in p.get(rule_list, []) or []:
                    if isinstance(rule, dict):
                        _repair_rule(rule, repairs)
            if "tolerance" in p and isinstance(p["tolerance"], str):
                coerced = _coerce_number(p["tolerance"])
                if coerced != p["tolerance"]:
                    p["tolerance"] = coerced
                    repairs.append("coerced string pass tolerance -> number")

    # Missing governance blocks get deterministic defaults.
    if "autonomy_config" not in cfg:
        cfg["autonomy_config"] = copy.deepcopy(DEFAULT_AUTONOMY_CONFIG)
        repairs.append("injected default autonomy_config")
    else:
        auto = cfg["autonomy_config"]
        if isinstance(auto, dict) and isinstance(auto.get("stp_confidence_threshold"), str):
            coerced = _coerce_number(auto["stp_confidence_threshold"])
            if coerced != auto["stp_confidence_threshold"]:
                auto["stp_confidence_threshold"] = coerced
                repairs.append("coerced string stp_confidence_threshold -> number")

    if "output_hash_spec" not in cfg:
        cfg["output_hash_spec"] = copy.deepcopy(DEFAULT_OUTPUT_HASH_SPEC)
        repairs.append("injected default output_hash_spec")

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
