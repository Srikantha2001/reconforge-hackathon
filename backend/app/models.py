"""The six-table data model (§6).

Postgres-native, but the generic SQLAlchemy JSON type also runs on SQLite so the
same models back the test suite. `audit_log` cross-references every table so the
question "which rules produced which results" is always answerable.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ReconConfig(Base):
    """A versioned reconciliation config and its approval state."""

    __tablename__ = "recon_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recon_name: Mapped[str] = mapped_column(String(200), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    config_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    english_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # draft -> approved. A run may only use an approved config.
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    author_id: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    approver_id: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    # Lineage: which prior version this one refined (Loop A / re-version).
    parent_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("recon_config.id"), nullable=True
    )
    origin: Mapped[str] = mapped_column(String(40), default="authoring")  # authoring | loop_a
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    approved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    runs: Mapped[list["Run"]] = relationship(back_populates="config")


class Run(Base):
    """One execution of an approved config against a file pair."""

    __tablename__ = "run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    config_id: Mapped[int] = mapped_column(ForeignKey("recon_config.id"), index=True)
    config_version: Mapped[int] = mapped_column(Integer)
    file_a_ref: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    file_b_ref: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    matched_count: Mapped[int] = mapped_column(Integer, default=0)
    break_count: Mapped[int] = mapped_column(Integer, default=0)
    total_a: Mapped[int] = mapped_column(Integer, default=0)
    total_b: Mapped[int] = mapped_column(Integer, default=0)
    match_rate: Mapped[float] = mapped_column(Float, default=0.0)
    output_hash: Mapped[str] = mapped_column(String(64), index=True)
    actor_id: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    config: Mapped["ReconConfig"] = relationship(back_populates="runs")
    breaks: Mapped[list["Break"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class Break(Base):
    """A record that did not reconcile, with agent advisory attached."""

    __tablename__ = "break"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("run.id"), index=True)
    # A natural, run-stable key so the reproducibility hash can order breaks.
    break_key: Mapped[str] = mapped_column(String(200), index=True)
    row_a: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    row_b: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    failed_rules: Mapped[list[Any]] = mapped_column(JSON, default=list)
    deltas: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    archetype: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    suggested_resolution: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sme_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    judge_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    judge_decision: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    severity: Mapped[str] = mapped_column(String(20), default="medium")
    # open | resolved | routed_to_human
    status: Mapped[str] = mapped_column(String(30), default="open", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    run: Mapped["Run"] = relationship(back_populates="breaks")


class ManualMatch(Base):
    """A human-confirmed pairing of two rows — the raw signal for Loop A."""

    __tablename__ = "manual_match"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("run.id"), index=True)
    break_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("break.id"), nullable=True
    )
    row_a: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    row_b: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    deltas: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    actor_id: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ResolutionMemory(Base):
    """Confirmed (break features -> archetype/resolution) for Loop B recall."""

    __tablename__ = "resolution_memory"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Canonical string form of feature_vector, for exact-match lookups across
    # both Postgres and SQLite (JSON equality isn't portable). feature_vector
    # itself remains the transparent/auditable full record.
    feature_key: Mapped[str] = mapped_column(String(300), index=True)
    feature_vector: Mapped[dict[str, Any]] = mapped_column(JSON)
    archetype: Mapped[str] = mapped_column(String(80), index=True)
    resolution: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float, default=0.9)
    times_seen: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class AuditLog(Base):
    """Append-only trail: actor, action, before/after, agent reasoning."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_id: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    entity_type: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    entity_id: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    before: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    after: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    agent_reasoning: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
