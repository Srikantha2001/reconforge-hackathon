"""Pydantic request/response models."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class Actor(BaseModel):
    id: str
    display_name: str


class AuthorConfigRequest(BaseModel):
    recon_name_hint: Optional[str] = None
    nl_description: str
    actor_id: str
    columns_a: List[str]
    columns_b: List[str]


class EditConfigRequest(BaseModel):
    config_json: Dict[str, Any]
    actor_id: str


class ApproveConfigRequest(BaseModel):
    actor_id: str


class ConfigOut(BaseModel):
    id: int
    recon_name: str
    version: int
    config_json: Dict[str, Any]
    english_summary: Optional[str]
    status: str
    author_id: Optional[str]
    approver_id: Optional[str]
    parent_id: Optional[int]
    origin: str
    created_at: datetime
    approved_at: Optional[datetime]
    repairs_applied: List[str] = []

    model_config = {"from_attributes": True}


class RunOut(BaseModel):
    id: int
    config_id: int
    config_version: int
    matched_count: int
    break_count: int
    total_a: int
    total_b: int
    match_rate: float
    output_hash: str
    actor_id: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class ReproducibilityCheckOut(BaseModel):
    run_id: int
    original_hash: str
    recomputed_hash: str
    reproducible: bool


class BreakOut(BaseModel):
    id: int
    run_id: int
    break_key: str
    row_a: Optional[Dict[str, Any]]
    row_b: Optional[Dict[str, Any]]
    failed_rules: List[Any]
    deltas: Dict[str, Any]
    archetype: Optional[str]
    explanation: Optional[str]
    suggested_resolution: Optional[str]
    sme_confidence: Optional[float]
    judge_confidence: Optional[float]
    judge_decision: Optional[str]
    severity: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class AdviseRequest(BaseModel):
    actor_id: str


class AdviseOut(BaseModel):
    break_id: int
    archetype: str
    label: str
    explanation: str
    suggested_resolution: str
    sme_confidence: float
    judge_decision: str
    judge_confidence: float
    judge_reason: str
    source: str  # "resolution_memory" | "llm" | "stub"


class ChaserOut(BaseModel):
    to: str
    subject: str
    body: str


class ManualMatchRequest(BaseModel):
    actor_id: str
    row_a: Optional[Dict[str, Any]] = None
    row_b: Optional[Dict[str, Any]] = None


class ResolveBreakRequest(BaseModel):
    actor_id: str
    confirmed_archetype: str
    confirmed_resolution: str


class LoopAAggregateGroup(BaseModel):
    field_a: str
    field_b: str
    type: str
    observed_deltas: List[float]
    count: int


class LoopAProposeRequest(BaseModel):
    actor_id: str
    field_a: str
    field_b: str
    type: str


class LoopAProposeOut(BaseModel):
    new_config: ConfigOut
    rationale: str


class LoopAWhatIfRequest(BaseModel):
    candidate_config_id: int


class LoopAWhatIfOut(BaseModel):
    current_match_rate: float
    candidate_match_rate: float
    current_matched: int
    candidate_matched: int
    newly_matched_keys: List[str]
    newly_broken_keys: List[str]


class AuditLogOut(BaseModel):
    id: int
    actor_id: Optional[str]
    action: str
    entity_type: Optional[str]
    entity_id: Optional[str]
    before: Optional[Dict[str, Any]]
    after: Optional[Dict[str, Any]]
    agent_reasoning: Optional[str]
    confidence: Optional[float]
    timestamp: datetime

    model_config = {"from_attributes": True}


class DashboardOut(BaseModel):
    run: RunOut
    archetype_counts: Dict[str, int]
    severity_counts: Dict[str, int]
    status_counts: Dict[str, int]


class ResolutionMemoryOut(BaseModel):
    id: int
    feature_key: str
    archetype: str
    resolution: str
    confidence: float
    times_seen: int

    model_config = {"from_attributes": True}
