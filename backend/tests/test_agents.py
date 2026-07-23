"""Agent layer v2 (P7 acceptance): classifier, SME, Judge, Loop A.

Drives the *real* engine-produced seed breaks through the classifier and SME,
checks the Judge routing bands (incl. TRD022 → REGULATORY_ESCALATION regardless
of confidence, and a low-confidence break → refuse + ESCALATE_SENIOR), and Loop
A proposing 2→3 days (capped at 5) from the four drift matches.
"""
import copy

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db import SessionLocal
from app import models
from app.agents import (
    ESCALATE_SENIOR,
    MAKER_REVIEW_REQUIRED,
    REGULATORY_ESCALATION,
    STP_AUTO_RESOLVE,
    detect_loop_a_pattern,
    judge_route,
    propose_loop_a_change,
    retrieve_similar_cases,
    sme_analyze,
)
from app.engine.archetype import ARCHETYPES, classify
from app.engine.runner import reconcile
from app.seed.generator import DEFAULT_CONFIG, generate, load_aux
from app.config_schema import validate


@pytest.fixture(scope="module")
def seed_breaks():
    df_a, df_b, cfg = generate()
    result = reconcile(df_a, df_b, cfg, aux_data=load_aux())
    by_isin = {}
    for b in result.breaks:
        by_isin.setdefault(b["isin"], []).append(b)
    return {"result": result, "by_isin": by_isin}


def _break(seed_breaks, isin):
    return seed_breaks["by_isin"][isin][0]


# --- Classifier over the real seed breaks -----------------------------------
def test_drift_break_classified(seed_breaks):
    res = classify(_break(seed_breaks, "DE000BAY0017"))  # TRD008
    assert res["archetype"] == "settlement_date_drift"
    assert res["causal_origin"] == "SETTLEMENT_TIMING_LAG"
    assert res["field_most_responsible"] == "settlement_date"
    # 3-layer root-cause tree is populated.
    tree = res["root_cause_tree"]
    assert set(tree) == {"data_layer", "rule_that_failed", "ai_diagnosis"}
    assert tree["ai_diagnosis"]["primary_hypothesis"]


def test_account_misbooking_classified(seed_breaks):
    res = classify(_break(seed_breaks, "IE00B4L5Y983"))  # TRD021
    assert res["archetype"] == "account_misbooking"
    assert res["causal_origin"] == "LEGAL_ENTITY_MISBOOKING"


def test_emir_dispute_classified(seed_breaks):
    res = classify(_break(seed_breaks, "XS0149080666"))  # TRD022
    assert res["archetype"] == "emir_amount_dispute"
    assert res["confidence"] >= 0.9


def test_missing_leg_classified(seed_breaks):
    res = classify(_break(seed_breaks, "LU0323578657"))  # TRD019
    assert res["archetype"] == "missing_leg"
    assert res["confidence"] < 0.65  # deliberately uncertain


def test_duplicate_classified(seed_breaks):
    dup = next(b for b in seed_breaks["result"].breaks if b["archetype"] == "duplicate_entry")
    res = classify(dup)
    assert res["archetype"] == "duplicate_entry"


def test_corporate_action_classified(seed_breaks):
    ca = seed_breaks["result"].explained_breaks[0]  # TRD024
    res = classify(ca)
    assert res["archetype"] == "corporate_action_adjustment"
    assert res["causal_origin"] == "CORPORATE_ACTION_PROCESSING_LAG"


def test_all_archetypes_are_known():
    for a in ARCHETYPES:
        assert isinstance(a, str)
    assert len(ARCHETYPES) == 12


# --- SME agent --------------------------------------------------------------
def test_sme_analyze_drift(seed_breaks):
    sme = sme_analyze(_break(seed_breaks, "DE000BAY0017"))
    assert sme["archetype"] == "settlement_date_drift"
    assert sme["suggested_resolution"]
    assert sme["refuse_to_classify"] is False


def test_sme_refuses_low_confidence(seed_breaks):
    sme = sme_analyze(_break(seed_breaks, "LU0323578657"))  # missing_leg, 0.60
    assert sme["refuse_to_classify"] is True
    assert sme["refuse_reason"]


# --- Judge routing bands ----------------------------------------------------
def test_judge_regulatory_wins_over_high_confidence(seed_breaks):
    sme = sme_analyze(_break(seed_breaks, "XS0149080666"))  # conf 0.90
    decision = judge_route(sme, regulatory_escalation_required=True)
    assert decision["autonomy_route"] == REGULATORY_ESCALATION  # regardless of confidence


def test_judge_low_confidence_escalates(seed_breaks):
    sme = sme_analyze(_break(seed_breaks, "LU0323578657"))  # conf 0.60
    decision = judge_route(sme, regulatory_escalation_required=False)
    assert decision["autonomy_route"] == ESCALATE_SENIOR


def test_judge_high_confidence_auto_resolves(seed_breaks):
    sme = sme_analyze(_break(seed_breaks, "XS0149080666"))  # conf 0.90 >= threshold
    decision = judge_route(sme, regulatory_escalation_required=False)
    assert decision["autonomy_route"] == STP_AUTO_RESOLVE


def test_judge_mid_confidence_maker_review(seed_breaks):
    sme = sme_analyze(_break(seed_breaks, "DE000BAY0017"))  # conf 0.85 -> review band
    decision = judge_route(sme, regulatory_escalation_required=False)
    assert decision["autonomy_route"] == MAKER_REVIEW_REQUIRED


# --- Loop B recall bumps usage ---------------------------------------------
def test_retrieve_similar_bumps_usage():
    with TestClient(app):  # ensure tables exist
        db = SessionLocal()
        try:
            mem = models.ResolutionMemory(
                feature_key="settlement_date_drift|AB|X",
                feature_vector={}, archetype="settlement_date_drift",
                causal_origin="SETTLEMENT_TIMING_LAG", resolution="Widen date tolerance.",
                confidence=0.9, times_seen=1, usage_count=0,
            )
            db.add(mem)
            db.commit()
            mem_id = mem.id
            cases = retrieve_similar_cases(db, "settlement_date_drift", "SETTLEMENT_TIMING_LAG")
            assert len(cases) >= 1
            db.refresh(mem)
            assert db.get(models.ResolutionMemory, mem_id).usage_count == 1
        finally:
            db.close()


# --- Loop A pattern detection + proposal ------------------------------------
def _drift_matches(n=4, delta=3):
    return [{"deltas": {"settlement_date:EXACT": delta}} for _ in range(n)]


def test_loop_a_detects_drift_and_proposes_widening():
    pattern = detect_loop_a_pattern(_drift_matches(4, 3))
    assert pattern == {"pattern": "date_drift", "delta": 3, "count": 4}

    proposal = propose_loop_a_change(DEFAULT_CONFIG, pattern)
    cfg = proposal["proposed_config"]
    # Date tolerance widened from 2 to 3, version minor-bumped, still valid.
    tol_days = [
        r["tolerance_days"]
        for p in cfg["matching_waterfall"]
        for r in p.get("value_rules", [])
        if r.get("match_type") == "DATE_TOLERANCE"
    ]
    assert all(d == 3 for d in tol_days) and tol_days
    assert cfg["version"] == "1.1.0"
    assert cfg["status"] == "DRAFT"
    assert validate(cfg) == []
    assert proposal["cap_note"] is None


def test_loop_a_below_threshold_no_pattern():
    assert detect_loop_a_pattern(_drift_matches(3, 3)) is None  # only 3, need 4


def test_loop_a_caps_date_tolerance_at_five():
    pattern = detect_loop_a_pattern(_drift_matches(4, 7))  # 7-day drift
    proposal = propose_loop_a_change(DEFAULT_CONFIG, pattern)
    cfg = proposal["proposed_config"]
    tol_days = [
        r["tolerance_days"]
        for p in cfg["matching_waterfall"]
        for r in p.get("value_rules", [])
        if r.get("match_type") == "DATE_TOLERANCE"
    ]
    assert all(d == 5 for d in tol_days)  # capped, never 7
    assert "cap" in proposal["cap_note"].lower()


def test_original_config_not_mutated_by_proposal():
    before = copy.deepcopy(DEFAULT_CONFIG)
    propose_loop_a_change(DEFAULT_CONFIG, {"pattern": "date_drift", "delta": 3, "count": 4})
    assert DEFAULT_CONFIG == before  # deepcopy isolation
