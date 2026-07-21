"""Provider-agnostic LLM interface.

The LLM authors config at design-time and advises on breaks post-run — it
never matches transactions (§2 law 1). Concretely that means:

  - `author_config` / `propose_config_change` return a config dict that MUST
    still pass app.config_schema.validate_and_repair before it is trusted.
  - `sme_explain` enriches (never overrides) the archetype/confidence that
    app.engine.archetype already computed deterministically from deltas —
    the archetype itself is grounded, only the prose may be provider-specific.
  - `judge_evaluate` only ever returns accept | route_to_human — it cannot
    change a match/break outcome.
  - `draft_chaser` produces a draft only; nothing here ever sends anything.

Every method must be resilient: if the underlying provider errors or returns
something unusable, the caller falls back to StubProvider's deterministic
output (fallback ladder rung #3) rather than raising.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class LLMProvider(ABC):
    name: str = "base"

    @abstractmethod
    def author_config(
        self, nl_description: str, columns_a: List[str], columns_b: List[str]
    ) -> Dict[str, Any]:
        """NL + column headers -> a (possibly not-yet-valid) config dict."""

    @abstractmethod
    def summarize_config(self, config: Dict[str, Any]) -> str:
        """Plain-English summary of an approved/pending config — the artifact
        ops actually read before approving (§11 OPEN point 1)."""

    @abstractmethod
    def sme_explain(
        self, break_row: Dict[str, Any], base_archetype: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Enrich the deterministic archetype classification with explanation
        prose and a suggested resolution. Must return
        {archetype, label, explanation, suggested_resolution, confidence} —
        archetype/confidence should normally just pass base_archetype through."""

    @abstractmethod
    def judge_evaluate(
        self, sme_result: Dict[str, Any], break_row: Dict[str, Any], threshold: float
    ) -> Dict[str, Any]:
        """Return {decision: 'accept'|'route_to_human', confidence, reason}."""

    @abstractmethod
    def draft_chaser(self, break_row: Dict[str, Any]) -> Dict[str, Any]:
        """Return {to, subject, body} — a draft only, never sent."""

    @abstractmethod
    def propose_config_change(
        self, current_config: Dict[str, Any], aggregated_deltas: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Loop A: given aggregated manual-match deltas, propose a new config
        dict (e.g. a widened tolerance) + a human-readable rationale. Returns
        {proposed_config, rationale}. Must still pass schema validation."""
