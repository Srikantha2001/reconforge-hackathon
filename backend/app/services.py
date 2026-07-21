"""Orchestration layer: ties the deterministic engine, the pluggable LLM
provider, and the six-table persistence model together. Routers stay thin;
all of the "what does an action actually do" logic lives here.
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from sqlalchemy.orm import Session

from . import models
from .config import get_settings
from .engine import archetype as archetype_mod
from .engine.runner import ReconResult, reconcile
from .llm.base import LLMProvider

settings = get_settings()


# --------------------------------------------------------------------------
# Audit
# --------------------------------------------------------------------------
def audit(
    db: Session,
    *,
    actor_id: Optional[str],
    action: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    before: Optional[Dict[str, Any]] = None,
    after: Optional[Dict[str, Any]] = None,
    agent_reasoning: Optional[str] = None,
    confidence: Optional[float] = None,
) -> models.AuditLog:
    entry = models.AuditLog(
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        before=before,
        after=after,
        agent_reasoning=agent_reasoning,
        confidence=confidence,
    )
    db.add(entry)
    return entry


# --------------------------------------------------------------------------
# CSV I/O
# --------------------------------------------------------------------------
def read_csv_bytes(content: bytes) -> pd.DataFrame:
    return pd.read_csv(io.BytesIO(content))


def read_csv_path(path: str) -> pd.DataFrame:
    return pd.read_csv(path)


def save_bytes(content: bytes, dest_dir: Path, filename: str) -> str:
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / filename
    dest.write_bytes(content)
    return str(dest)


# --------------------------------------------------------------------------
# Runs
# --------------------------------------------------------------------------
def execute_run(
    db: Session,
    *,
    config: models.ReconConfig,
    df_a: pd.DataFrame,
    df_b: pd.DataFrame,
    file_a_ref: Optional[str],
    file_b_ref: Optional[str],
    actor_id: str,
) -> models.Run:
    result: ReconResult = reconcile(df_a, df_b, config.config_json)

    run = models.Run(
        config_id=config.id,
        config_version=config.version,
        file_a_ref=file_a_ref,
        file_b_ref=file_b_ref,
        matched_count=result.matched_count,
        break_count=result.break_count,
        total_a=result.total_a,
        total_b=result.total_b,
        match_rate=result.match_rate,
        output_hash=result.output_hash,
        actor_id=actor_id,
    )
    db.add(run)
    db.flush()  # assign run.id

    for b in result.breaks:
        db.add(
            models.Break(
                run_id=run.id,
                break_key=b["break_key"],
                row_a=b["row_a"],
                row_b=b["row_b"],
                failed_rules=b["failed_rules"],
                deltas=b["deltas"],
                # The archetype/explanation/confidence are already fully
                # determined here by the deterministic engine (§7: "doubles
                # as the no-LLM fallback for the SME agent") — the /advise
                # endpoint enriches this later, it doesn't invent it.
                archetype=b["archetype"],
                explanation=b["explanation"],
                sme_confidence=b["sme_confidence"],
                severity=b["severity"],
                status="open",
            )
        )

    audit(
        db,
        actor_id=actor_id,
        action="run_executed",
        entity_type="run",
        entity_id=None,  # filled by caller after flush if needed
        after={
            "config_id": config.id,
            "config_version": config.version,
            "matched_count": result.matched_count,
            "break_count": result.break_count,
            "match_rate": result.match_rate,
            "output_hash": result.output_hash,
        },
    )
    db.flush()
    return run


def reproducibility_check(db: Session, run: models.Run) -> Tuple[str, bool]:
    """Re-run the engine on the SAME stored files + config version and compare
    hashes — the automated test behind §2 law 4, exposed as an API action."""
    df_a = read_csv_path(run.file_a_ref)
    df_b = read_csv_path(run.file_b_ref)
    result = reconcile(df_a, df_b, run.config.config_json)
    return result.output_hash, result.output_hash == run.output_hash


# --------------------------------------------------------------------------
# Break advisory (SME + Judge, with Loop B short-circuit)
# --------------------------------------------------------------------------
def _rule_types_from_failed(failed_rules: List[str]) -> List[str]:
    return sorted({r.split(":")[-1] for r in failed_rules if ":" in r})


def feature_key_for_break(brk: models.Break) -> str:
    side = "two_sided" if (brk.row_a and brk.row_b) else ("one_sided_a" if brk.row_b is None else "one_sided_b")
    rule_types = _rule_types_from_failed(brk.failed_rules or [])
    return f"{brk.archetype}|{side}|{','.join(rule_types)}|{brk.severity}"


def break_row_dict(brk: models.Break) -> Dict[str, Any]:
    return {
        "break_key": brk.break_key,
        "row_a": brk.row_a,
        "row_b": brk.row_b,
        "deltas": brk.deltas,
        "archetype_label": archetype_mod.ARCHETYPE_LABELS.get(brk.archetype, brk.archetype),
        "explanation": brk.explanation,
    }


def lookup_resolution_memory(db: Session, feature_key: str) -> Optional[models.ResolutionMemory]:
    return (
        db.query(models.ResolutionMemory)
        .filter(models.ResolutionMemory.feature_key == feature_key)
        .order_by(models.ResolutionMemory.confidence.desc())
        .first()
    )


def upsert_resolution_memory(
    db: Session,
    *,
    feature_key: str,
    feature_vector: Dict[str, Any],
    archetype: str,
    resolution: str,
    confidence: float,
) -> models.ResolutionMemory:
    existing = lookup_resolution_memory(db, feature_key)
    if existing:
        existing.times_seen += 1
        existing.confidence = min(0.99, max(existing.confidence, confidence) + 0.03)
        existing.resolution = resolution
        return existing
    entry = models.ResolutionMemory(
        feature_key=feature_key,
        feature_vector=feature_vector,
        archetype=archetype,
        resolution=resolution,
        confidence=confidence,
        times_seen=1,
    )
    db.add(entry)
    return entry


def advise_break(
    db: Session, *, brk: models.Break, actor_id: str, provider: LLMProvider, threshold: float
) -> Dict[str, Any]:
    base_archetype = {
        "archetype": brk.archetype,
        "label": archetype_mod.ARCHETYPE_LABELS.get(brk.archetype, brk.archetype),
        "explanation": brk.explanation,
        "confidence": brk.sme_confidence,
    }
    feature_key = feature_key_for_break(brk)
    mem = lookup_resolution_memory(db, feature_key)

    source = "stub" if provider.name == "stub" else "llm"
    if mem and mem.confidence >= threshold:
        sme_result = {
            "archetype": brk.archetype,
            "label": base_archetype["label"],
            "explanation": (
                f"{base_archetype['explanation']} This pattern has been confirmed "
                f"{mem.times_seen} time(s) before."
            ),
            "suggested_resolution": mem.resolution,
            "confidence": mem.confidence,
        }
        source = "resolution_memory"
    else:
        sme_result = provider.sme_explain(break_row_dict(brk), base_archetype)

    judge_result = provider.judge_evaluate(sme_result, break_row_dict(brk), threshold)

    before_status = brk.status
    brk.explanation = sme_result["explanation"]
    brk.suggested_resolution = sme_result["suggested_resolution"]
    brk.sme_confidence = sme_result["confidence"]
    brk.judge_confidence = judge_result["confidence"]
    brk.judge_decision = judge_result["decision"]
    brk.status = "auto_accepted" if judge_result["decision"] == "accept" else "routed_to_human"

    audit(
        db,
        actor_id=actor_id,
        action="break_advised",
        entity_type="break",
        entity_id=brk.id,
        before={"status": before_status},
        after={"status": brk.status, "decision": judge_result["decision"]},
        agent_reasoning=f"SME: {sme_result['explanation']} | Judge: {judge_result['reason']}",
        confidence=judge_result["confidence"],
    )

    return {
        "break_id": brk.id,
        "archetype": brk.archetype,
        "label": base_archetype["label"],
        "explanation": sme_result["explanation"],
        "suggested_resolution": sme_result["suggested_resolution"],
        "sme_confidence": sme_result["confidence"],
        "judge_decision": judge_result["decision"],
        "judge_confidence": judge_result["confidence"],
        "judge_reason": judge_result["reason"],
        "source": source,
    }


def resolve_break(
    db: Session,
    *,
    brk: models.Break,
    actor_id: str,
    confirmed_archetype: str,
    confirmed_resolution: str,
) -> models.ResolutionMemory:
    """Human confirms a resolution -> Loop B stores/reinforces the memory
    entry. This is the only way resolution_memory changes — never silently."""
    feature_key = feature_key_for_break(brk)
    feature_vector = {
        "archetype": confirmed_archetype,
        "side": "two_sided" if (brk.row_a and brk.row_b) else ("one_sided_a" if brk.row_b is None else "one_sided_b"),
        "failed_rule_types": _rule_types_from_failed(brk.failed_rules or []),
        "severity": brk.severity,
    }
    before_status = brk.status
    brk.status = "resolved"
    brk.archetype = confirmed_archetype
    brk.suggested_resolution = confirmed_resolution

    mem = upsert_resolution_memory(
        db,
        feature_key=feature_key,
        feature_vector=feature_vector,
        archetype=confirmed_archetype,
        resolution=confirmed_resolution,
        confidence=max(brk.sme_confidence or 0.7, 0.7),
    )

    audit(
        db,
        actor_id=actor_id,
        action="break_resolved",
        entity_type="break",
        entity_id=brk.id,
        before={"status": before_status},
        after={"status": "resolved", "archetype": confirmed_archetype},
    )
    return mem


# --------------------------------------------------------------------------
# Loop A: manual matches -> aggregated deltas -> proposed config change
# --------------------------------------------------------------------------
def record_manual_match(
    db: Session,
    *,
    run: models.Run,
    brk: Optional[models.Break],
    row_a: Dict[str, Any],
    row_b: Dict[str, Any],
    actor_id: str,
) -> models.ManualMatch:
    from .engine.matching import evaluate_pair

    rules = run.config.config_json["match_rules"]
    _, rule_results = evaluate_pair(rules, row_a, row_b)
    deltas = {r["rule"]: r["delta"] for r in rule_results if not r["passed"]}

    mm = models.ManualMatch(
        run_id=run.id,
        break_id=brk.id if brk else None,
        row_a=row_a,
        row_b=row_b,
        deltas=deltas,
        actor_id=actor_id,
    )
    db.add(mm)

    if brk is not None:
        before_status = brk.status
        brk.status = "resolved"
        audit(
            db,
            actor_id=actor_id,
            action="manual_match_recorded",
            entity_type="break",
            entity_id=brk.id,
            before={"status": before_status},
            after={"status": "resolved"},
        )
    return mm


def aggregate_manual_matches(db: Session, run_id: int) -> List[Dict[str, Any]]:
    """Group this run's manual matches by which rule they disagreed on."""
    matches = db.query(models.ManualMatch).filter(models.ManualMatch.run_id == run_id).all()
    groups: Dict[str, Dict[str, Any]] = {}
    for m in matches:
        for rule_key, delta in (m.deltas or {}).items():
            if delta is None:
                continue
            # rule_key looks like "field_a<->field_b:type"
            try:
                fields_part, rtype = rule_key.split(":")
                field_a, field_b = fields_part.split("<->")
            except ValueError:
                continue
            g = groups.setdefault(
                rule_key, {"field_a": field_a, "field_b": field_b, "type": rtype, "observed_deltas": []}
            )
            g["observed_deltas"].append(delta)

    return [
        {**g, "count": len(g["observed_deltas"])}
        for g in groups.values()
        if len(g["observed_deltas"]) > 0
    ]


def propose_loop_a_config(
    db: Session,
    *,
    current_config: models.ReconConfig,
    group: Dict[str, Any],
    provider: LLMProvider,
    actor_id: str,
) -> Tuple[models.ReconConfig, str]:
    from .config_schema import validate_and_repair

    result = provider.propose_config_change(current_config.config_json, group)
    proposed_raw = result["proposed_config"]
    rationale = result["rationale"]

    valid_config, repairs = validate_and_repair(proposed_raw)

    new_version = models.ReconConfig(
        recon_name=current_config.recon_name,
        version=current_config.version + 1,
        config_json=valid_config,
        english_summary=provider.summarize_config(valid_config),
        status="draft",
        author_id=actor_id,
        parent_id=current_config.id,
        origin="loop_a",
    )
    db.add(new_version)
    db.flush()

    audit(
        db,
        actor_id=actor_id,
        action="loop_a_proposed",
        entity_type="recon_config",
        entity_id=new_version.id,
        before={"parent_version": current_config.version},
        after={"new_version": new_version.version, "rationale": rationale, "repairs": repairs},
        agent_reasoning=rationale,
    )
    return new_version, rationale


def what_if(
    db: Session, *, run: models.Run, candidate_config: models.ReconConfig
) -> Dict[str, Any]:
    df_a = read_csv_path(run.file_a_ref)
    df_b = read_csv_path(run.file_b_ref)

    current_result = reconcile(df_a, df_b, run.config.config_json)
    candidate_result = reconcile(df_a, df_b, candidate_config.config_json)

    current_keys = {m["key"] for m in current_result.matched}
    candidate_keys = {m["key"] for m in candidate_result.matched}

    return {
        "current_match_rate": current_result.match_rate,
        "candidate_match_rate": candidate_result.match_rate,
        "current_matched": current_result.matched_count,
        "candidate_matched": candidate_result.matched_count,
        "newly_matched_keys": sorted(candidate_keys - current_keys),
        "newly_broken_keys": sorted(current_keys - candidate_keys),
    }
