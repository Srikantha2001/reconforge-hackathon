"""Pydantic request/response models."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class Actor(BaseModel):
    id: str
    display_name: str


# --- Auth (P4) -------------------------------------------------------------
class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    role: str
    email: str
    name: str


class UserOut(BaseModel):
    user_id: str
    email: str
    role: str


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
    recon_type: str = "POSITION"
    version: str  # semver (v2) — e.g. "1.0.0"
    config_json: Dict[str, Any]
    english_summary: Optional[str]
    status: str  # DRAFT | PENDING_APPROVAL | APPROVED | SUPERSEDED
    author_id: Optional[str]
    approver_id: Optional[str]
    parent_id: Optional[int]
    superseded_by: Optional[int] = None
    origin: str
    created_at: datetime
    approved_at: Optional[datetime]
    repairs_applied: List[str] = []

    model_config = {"from_attributes": True}


class RunOut(BaseModel):
    id: int
    config_id: int
    config_version: str  # semver (v2)
    matched_count: int
    break_count: int
    total_a: int
    total_b: int
    match_rate: float
    position_proof_status: Optional[str] = None
    regulatory_escalation_count: int = 0
    duration_ms: Optional[int] = None
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
    side: Optional[str] = None
    row_a: Optional[Dict[str, Any]]
    row_b: Optional[Dict[str, Any]]
    failed_rules: List[Any]
    deltas: Dict[str, Any]
    isin: Optional[str] = None
    currency: Optional[str] = None
    asset_class: Optional[str] = None
    pass_that_failed: Optional[int] = None
    archetype: Optional[str]
    causal_origin: Optional[str] = None
    field_most_responsible: Optional[str] = None
    root_cause_tree: Optional[Dict[str, Any]] = None
    explanation: Optional[str]
    regulatory_narrative: Optional[str] = None
    suggested_resolution: Optional[str]
    sme_confidence: Optional[float]
    judge_confidence: Optional[float]
    judge_decision: Optional[str]
    autonomy_route: Optional[str] = None
    regulatory_escalation_required: bool = False
    age_business_days: int = 0
    severity: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


# --- Config workflow + runs + breaks + client portal (P8) ------------------
class AuthorConfigV2Request(BaseModel):
    nl_description: str = ""
    recon_name_hint: Optional[str] = None


class ConfigDecisionRequest(BaseModel):
    approved: bool = True
    notes: Optional[str] = None


class PositionProofOut(BaseModel):
    side: str
    status: str
    opening: float
    computed_closing: float
    stated_closing: float
    variance: float
    unexplained_variance: float


class PassStatOut(BaseModel):
    pass_number: Optional[int] = None
    pass_name: Optional[str] = None
    match_type: Optional[str] = None
    matched_count: int
    pool_a_remaining: int
    pool_b_remaining: int


class RunSummaryOut(BaseModel):
    run: "RunOut"
    position_proof_status: Optional[str] = None
    archetype_counts: Dict[str, int]
    status_counts: Dict[str, int]
    regulatory_escalation_count: int


class AnalyzeRequest(BaseModel):
    run_id: int


class BreakAnalysisOut(BaseModel):
    break_id: int
    archetype: str
    causal_origin: str
    field_most_responsible: str
    confidence: float
    autonomy_route: str
    refuse_to_classify: bool
    routing_rationale: str


class LoopAProposeOutV2(BaseModel):
    new_config: "ConfigOut"
    rationale: str
    cap_note: Optional[str] = None


class ClientUploadOut(BaseModel):
    run_id: int
    match_rate: float
    matched_count: int
    break_count: int
    output_hash: str


class ClientBreakOut(BaseModel):
    break_id: int
    isin: Optional[str] = None
    issue: str  # plain-English archetype label
    status: str
    amount: Optional[float] = None


class ClientReconOut(BaseModel):
    run_id: int
    match_rate: float
    matched_count: int
    break_count: int
    breaks: List[ClientBreakOut]


class EvidencePack(BaseModel):
    run_id: int
    recon_name: str
    match_rate: float
    output_hash: str
    position_proof_status: Optional[str] = None
    break_count: int
    generated_at: str
    document_hash: str


# --- Regulatory (P6) -------------------------------------------------------
class RegulatoryNotificationOut(BaseModel):
    id: int
    break_id: int
    regime: str
    competent_authority: str
    notification_draft: str
    dispute_amount: Optional[float] = None
    dispute_days: Optional[int] = None
    status: str
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    filed_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class CassReconciliationOut(BaseModel):
    id: int
    reconciliation_date: str
    client_liability_total: float
    safeguarded_funds_total: float
    shortfall_amount: Optional[float] = None
    shortfall_status: str
    resolution_pack_hash: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# --- Governance (P5) -------------------------------------------------------
class MakerSubmitRequest(BaseModel):
    break_id: int
    action_type: str  # FORCE_MATCH | WRITE_OFF | INVESTIGATE | AWAIT_COUNTERPARTY
    notes: Optional[str] = None


class CheckerApproveRequest(BaseModel):
    action_id: int
    approved: bool
    notes: Optional[str] = None


class JournalEntryOut(BaseModel):
    id: int
    governance_action_id: int
    break_id: int
    entry_type: str
    debit_account: str
    credit_account: str
    quantity: Optional[float] = None
    amount: float
    currency: str
    isin: Optional[str] = None
    narrative: str
    approved_by: str
    approved_at: datetime
    audit_reference: str

    model_config = {"from_attributes": True}


class GovernanceActionOut(BaseModel):
    id: int
    break_id: int
    action_type: str
    maker_id: str
    checker_id: Optional[str] = None
    status: str
    maker_notes: Optional[str] = None
    checker_notes: Optional[str] = None
    rejection_reason: Optional[str] = None
    submitted_at: datetime
    decided_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class PendingActionOut(GovernanceActionOut):
    time_remaining_seconds: int


class MakerSubmitOut(BaseModel):
    action: GovernanceActionOut
    journal_entry: Optional[JournalEntryOut] = None  # set when a small write-off auto-approves


class CheckerDecisionOut(BaseModel):
    status: str
    journal_entry: Optional[JournalEntryOut] = None


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
    causal_origin: Optional[str] = None
    resolution: str
    confidence: float
    times_seen: int
    usage_count: int = 0

    model_config = {"from_attributes": True}
