"""ReconOS data model (P2 — docs/RECONOS_UPGRADE_PLAN.md §4).

The original six ReconForge tables (recon_config, run, break, manual_match,
resolution_memory, audit_log) are extended in place, and six new tables are
added (users, match_ledger, governance_action, journal_entry,
regulatory_notification, cass_reconciliation, loop_a_suggestion).

Laws enforced here:
- Monetary amounts and quantities are ``Numeric(20, 6)`` — never Float (Law 2).
- ``governance_action`` enforces maker != checker with a DB CheckConstraint,
  not just service code (Law 5).
- ``audit_log`` and ``match_ledger`` are append-only: the service layer must
  never UPDATE or DELETE rows in them (Laws 6/7) — there is deliberately no
  update path for either.
- ``journal_entry`` rows are export-only and never auto-posted (Law 9).

Adaptation notes (deliberate, documented in the plan):
- Integer autoincrement PKs are kept (the spec's TEXT PKs would break every
  existing service/router for no functional gain at this scale).
- Actor/user reference columns stay plain strings rather than hard FKs to
  ``users`` — P4 populates them with real user ids; SQLite does not enforce
  FKs by default anyway.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    """Demo users with roles — populated at startup from P4 on."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20))
    client_org: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    hashed_password: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    __table_args__ = (
        CheckConstraint(
            "role IN ('ADMIN','MAKER','CHECKER','CLIENT','DSI')",
            name="ck_users_role",
        ),
    )


class ReconConfig(Base):
    """A versioned reconciliation config and its approval state.

    v2: semver string versions, four-state lifecycle
    (DRAFT -> PENDING_APPROVAL -> APPROVED -> SUPERSEDED), recon typing,
    and supersession lineage. UNIQUE(recon_name, version).
    """

    __tablename__ = "recon_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recon_name: Mapped[str] = mapped_column(String(200), index=True)
    recon_type: Mapped[str] = mapped_column(String(40), default="POSITION")
    version: Mapped[str] = mapped_column(String(16), default="1.0.0")
    config_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    english_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="DRAFT", index=True)
    author_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    approver_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    # Lineage: which prior version this one refined (Loop A / re-version)…
    parent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("recon_config.id"), nullable=True)
    # …and which newer version superseded this one.
    superseded_by: Mapped[Optional[int]] = mapped_column(ForeignKey("recon_config.id"), nullable=True)
    origin: Mapped[str] = mapped_column(String(40), default="authoring")  # authoring | loop_a
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    runs: Mapped[list["Run"]] = relationship(back_populates="config", foreign_keys="Run.config_id")

    __table_args__ = (
        UniqueConstraint("recon_name", "version", name="uq_recon_config_name_version"),
        CheckConstraint(
            "status IN ('DRAFT','PENDING_APPROVAL','APPROVED','SUPERSEDED')",
            name="ck_recon_config_status",
        ),
    )


class Run(Base):
    """One execution of an approved config against a file pair."""

    __tablename__ = "run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    config_id: Mapped[int] = mapped_column(ForeignKey("recon_config.id"), index=True)
    config_version: Mapped[str] = mapped_column(String(16))
    file_a_ref: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    file_b_ref: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    matched_count: Mapped[int] = mapped_column(Integer, default=0)
    break_count: Mapped[int] = mapped_column(Integer, default=0)
    total_a: Mapped[int] = mapped_column(Integer, default=0)
    total_b: Mapped[int] = mapped_column(Integer, default=0)
    match_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)
    position_proof_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    regulatory_escalation_count: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    output_hash: Mapped[str] = mapped_column(String(64), index=True)
    actor_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    # Client-portal runs (P8): the owning client user and a flag, for isolation.
    client_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, index=True)
    is_client_run: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    config: Mapped["ReconConfig"] = relationship(back_populates="runs", foreign_keys=[config_id])
    breaks: Mapped[list["Break"]] = relationship(back_populates="run", cascade="all, delete-orphan")


class MatchLedger(Base):
    """APPEND-ONLY (Law 7): one row per match produced by a waterfall pass.

    The service layer must never UPDATE or DELETE match_ledger rows.
    """

    __tablename__ = "match_ledger"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("run.id"), index=True)
    pass_number: Mapped[int] = mapped_column(Integer)
    pass_name: Mapped[str] = mapped_column(String(120))
    match_type: Mapped[str] = mapped_column(String(40))
    row_ids_a: Mapped[str] = mapped_column(Text)  # comma-joined row_id list
    row_ids_b: Mapped[str] = mapped_column(Text)
    isin: Mapped[Optional[str]] = mapped_column(String(12), nullable=True)
    currency: Mapped[Optional[str]] = mapped_column(String(3), nullable=True)
    settlement_date: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    quantity_a: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 6), nullable=True)
    quantity_b: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 6), nullable=True)
    amount_a: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 6), nullable=True)
    amount_b: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 6), nullable=True)
    quantity_variance: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 6), nullable=True)
    amount_variance: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 6), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Break(Base):
    """A record that did not reconcile, with agent advisory attached."""

    __tablename__ = "break"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("run.id"), index=True)
    # A natural, run-stable key so the reproducibility hash can order breaks.
    break_key: Mapped[str] = mapped_column(String(200), index=True)
    side: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)  # A | B
    row_a: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    row_b: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    failed_rules: Mapped[list[Any]] = mapped_column(JSON, default=list)
    deltas: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    isin: Mapped[Optional[str]] = mapped_column(String(12), nullable=True, index=True)
    currency: Mapped[Optional[str]] = mapped_column(String(3), nullable=True)
    asset_class: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    quantity_a: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 6), nullable=True)
    quantity_b: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 6), nullable=True)
    amount_a: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 6), nullable=True)
    amount_b: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 6), nullable=True)
    quantity_variance: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 6), nullable=True)
    amount_variance: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 6), nullable=True)
    pass_that_failed: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    archetype: Mapped[Optional[str]] = mapped_column(String(80), nullable=True, index=True)
    causal_origin: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    field_most_responsible: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    root_cause_tree: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    regulatory_narrative: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    suggested_resolution: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sme_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    judge_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    judge_decision: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    autonomy_route: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    regulatory_escalation_required: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    age_business_days: Mapped[int] = mapped_column(Integer, default=0)
    severity: Mapped[str] = mapped_column(String(20), default="medium")
    status: Mapped[str] = mapped_column(String(40), default="open", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    run: Mapped["Run"] = relationship(back_populates="breaks")


class ManualMatch(Base):
    """A human-confirmed pairing of two rows — the raw signal for Loop A."""

    __tablename__ = "manual_match"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("run.id"), index=True)
    break_id: Mapped[Optional[int]] = mapped_column(ForeignKey("break.id"), nullable=True)
    row_a: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    row_b: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    deltas: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    actor_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class GovernanceAction(Base):
    """A maker-submitted action on a break awaiting checker decision.

    maker != checker is a DB constraint (Law 5), not just a service check.
    """

    __tablename__ = "governance_action"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    break_id: Mapped[int] = mapped_column(ForeignKey("break.id"), index=True)
    action_type: Mapped[str] = mapped_column(String(40))
    maker_id: Mapped[str] = mapped_column(String(120))
    checker_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="PENDING", index=True)
    maker_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    checker_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "checker_id IS NULL OR maker_id != checker_id",
            name="ck_governance_maker_neq_checker",
        ),
        CheckConstraint(
            "action_type IN ('FORCE_MATCH','WRITE_OFF','INVESTIGATE','AWAIT_COUNTERPARTY')",
            name="ck_governance_action_type",
        ),
        CheckConstraint(
            "status IN ('PENDING','APPROVED','REJECTED','EXPIRED')",
            name="ck_governance_status",
        ),
    )


class JournalEntry(Base):
    """Generated on checker approval. EXPORT-ONLY — never auto-posted (Law 9)."""

    __tablename__ = "journal_entry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    governance_action_id: Mapped[int] = mapped_column(ForeignKey("governance_action.id"))
    break_id: Mapped[int] = mapped_column(ForeignKey("break.id"))
    entry_type: Mapped[str] = mapped_column(String(40))
    debit_account: Mapped[str] = mapped_column(String(120))
    credit_account: Mapped[str] = mapped_column(String(120))
    quantity: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 6), nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 6))
    currency: Mapped[str] = mapped_column(String(3))
    isin: Mapped[Optional[str]] = mapped_column(String(12), nullable=True)
    narrative: Mapped[str] = mapped_column(Text)
    approved_by: Mapped[str] = mapped_column(String(120))
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    audit_reference: Mapped[str] = mapped_column(String(64))


class RegulatoryNotification(Base):
    """A drafted regulatory filing (EMIR/CASS/CSDR) awaiting human approval."""

    __tablename__ = "regulatory_notification"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    break_id: Mapped[int] = mapped_column(ForeignKey("break.id"), index=True)
    regime: Mapped[str] = mapped_column(String(40))
    competent_authority: Mapped[str] = mapped_column(String(120))
    notification_draft: Mapped[str] = mapped_column(Text)
    dispute_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 6), nullable=True)
    dispute_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="DRAFT", index=True)
    approved_by: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    filed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    __table_args__ = (
        CheckConstraint(
            "regime IN ('EMIR_ARTICLE_15','CASS_7A','CSDR_PENALTY')",
            name="ck_regnotif_regime",
        ),
        CheckConstraint(
            "status IN ('DRAFT','PENDING_APPROVAL','FILED')",
            name="ck_regnotif_status",
        ),
    )


class CassReconciliation(Base):
    """One CASS 7A daily reconciliation result (client money safeguarding)."""

    __tablename__ = "cass_reconciliation"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[Optional[int]] = mapped_column(ForeignKey("run.id"), nullable=True)
    reconciliation_date: Mapped[str] = mapped_column(String(10), index=True)
    client_liability_total: Mapped[Decimal] = mapped_column(Numeric(20, 6))
    safeguarded_funds_total: Mapped[Decimal] = mapped_column(Numeric(20, 6))
    shortfall_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 6), nullable=True)
    shortfall_status: Mapped[str] = mapped_column(String(30), default="NIL")
    resolution_pack_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    dsi_signed_off_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    __table_args__ = (
        CheckConstraint(
            "shortfall_status IN ('NIL','SHORTFALL_DETECTED','SHORTFALL_ESCALATED')",
            name="ck_cass_shortfall_status",
        ),
    )


class LoopASuggestion(Base):
    """A detected systemic pattern with a proposed config change (Loop A)."""

    __tablename__ = "loop_a_suggestion"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("run.id"), index=True)
    pattern_detected: Mapped[str] = mapped_column(Text)
    manual_match_count: Mapped[int] = mapped_column(Integer, default=0)
    proposed_config_change: Mapped[dict[str, Any]] = mapped_column(JSON)
    what_if_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="PENDING", index=True)
    approved_by: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    resulting_config_id: Mapped[Optional[int]] = mapped_column(ForeignKey("recon_config.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING','APPROVED','REJECTED')",
            name="ck_loop_a_status",
        ),
    )


class ResolutionMemory(Base):
    """Confirmed (break features -> archetype/resolution) for Loop B recall."""

    __tablename__ = "resolution_memory"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Canonical string form of feature_vector, for exact-match lookups.
    feature_key: Mapped[str] = mapped_column(String(300), index=True)
    feature_vector: Mapped[dict[str, Any]] = mapped_column(JSON)
    archetype: Mapped[str] = mapped_column(String(80), index=True)
    causal_origin: Mapped[Optional[str]] = mapped_column(String(80), nullable=True, index=True)
    resolution: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float, default=0.9)
    times_seen: Mapped[int] = mapped_column(Integer, default=1)
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class AuditLog(Base):
    """APPEND-ONLY (Law 6) trail: actor, action, before/after, agent reasoning.

    The service layer must never UPDATE or DELETE audit_log rows.
    """

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    entity_type: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    entity_id: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    before: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    after: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    agent_reasoning: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
