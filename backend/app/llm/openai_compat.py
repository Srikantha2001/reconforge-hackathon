"""OpenAI-compatible chat-completions adapter.

Works against the real OpenAI API and any gateway exposing an OpenAI-compatible
`/chat/completions` endpoint (set OPENAI_BASE_URL). Genuine Azure OpenAI uses a
different URL/auth shape (`/openai/deployments/{deployment}/...` +
`api-key` header); point OPENAI_BASE_URL at an Azure-OpenAI-compatible proxy,
or add a small subclass here if you need the native Azure route — the
provider-agnostic interface in base.py makes that a self-contained addition.

Same resilience posture as the Gemini adapter: every method falls back to the
deterministic StubProvider on any error.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

import httpx

from .base import LLMProvider
from .stub import StubProvider

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def _extract_json(text: str) -> Dict[str, Any]:
    m = _JSON_FENCE_RE.search(text)
    candidate = m.group(1) if m else text
    return json.loads(candidate)


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self, api_key: str, base_url: Optional[str] = None, model: Optional[str] = None):
        self._api_key = api_key
        self._base_url = (base_url or "https://api.openai.com/v1").rstrip("/")
        self._model = model or "gpt-4o-mini"
        self._fallback = StubProvider()

    def _chat(self, prompt: str) -> str:
        resp = httpx.post(
            f"{self._base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={
                "model": self._model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    def author_config(
        self, nl_description: str, columns_a: List[str], columns_b: List[str]
    ) -> Dict[str, Any]:
        prompt = (
            "You author reconciliation configs for a deterministic engine. "
            "Return ONLY a JSON object matching this exact shape (no prose):\n"
            '{"recon_name": str, '
            '"source_a": {"alias": str, "key_columns": [str]}, '
            '"source_b": {"alias": str, "key_columns": [str]}, '
            '"transforms": [{"field": str, "op": "abs|upper|lower|strip|round2", "side": "a|b|both"}], '
            '"match_rules": [{"field_a": str, "field_b": str, "type": "exact|numeric_tolerance|date_tolerance", '
            '"tolerance": number, "tolerance_days": int}]}\n'
            f"Only use column names from these actual headers — source_a columns: {columns_a}; "
            f"source_b columns: {columns_b}.\n"
            f"User's description of the reconciliation:\n{nl_description}"
        )
        try:
            return _extract_json(self._chat(prompt))
        except Exception:
            return self._fallback.author_config(nl_description, columns_a, columns_b)

    def summarize_config(self, config: Dict[str, Any]) -> str:
        prompt = (
            "Write a short, plain-English paragraph (no jargon) explaining exactly what this "
            "reconciliation config will do, for an ops person about to approve it:\n"
            f"{json.dumps(config)}"
        )
        try:
            text = self._chat(prompt).strip()
            return text or self._fallback.summarize_config(config)
        except Exception:
            return self._fallback.summarize_config(config)

    def sme_explain(
        self, break_row: Dict[str, Any], base_archetype: Dict[str, Any]
    ) -> Dict[str, Any]:
        prompt = (
            "A deterministic engine has already classified this reconciliation break — do NOT "
            "change the archetype or confidence, only write a clearer explanation and a concrete "
            "suggested resolution. Return ONLY JSON: "
            '{"explanation": str, "suggested_resolution": str}\n'
            f"Archetype: {base_archetype['archetype']} ({base_archetype['label']})\n"
            f"Deterministic explanation: {base_archetype['explanation']}\n"
            f"Row A: {json.dumps(break_row.get('row_a'))}\n"
            f"Row B: {json.dumps(break_row.get('row_b'))}\n"
            f"Failed rules/deltas: {json.dumps(break_row.get('deltas'))}"
        )
        try:
            data = _extract_json(self._chat(prompt))
            return {
                "archetype": base_archetype["archetype"],
                "label": base_archetype["label"],
                "explanation": data.get("explanation") or base_archetype["explanation"],
                "suggested_resolution": data.get("suggested_resolution")
                or self._fallback.sme_explain(break_row, base_archetype)["suggested_resolution"],
                "confidence": base_archetype["confidence"],
            }
        except Exception:
            return self._fallback.sme_explain(break_row, base_archetype)

    def judge_evaluate(
        self, sme_result: Dict[str, Any], break_row: Dict[str, Any], threshold: float
    ) -> Dict[str, Any]:
        return self._fallback.judge_evaluate(sme_result, break_row, threshold)

    def draft_chaser(self, break_row: Dict[str, Any]) -> Dict[str, Any]:
        prompt = (
            "Draft a short, polite email to a counterparty querying a reconciliation "
            "discrepancy. Return ONLY JSON: {\"to\": str, \"subject\": str, \"body\": str}\n"
            f"Break: {json.dumps({k: v for k, v in break_row.items() if k != 'rule_results'}, default=str)}"
        )
        try:
            data = _extract_json(self._chat(prompt))
            if all(k in data for k in ("to", "subject", "body")):
                return data
            return self._fallback.draft_chaser(break_row)
        except Exception:
            return self._fallback.draft_chaser(break_row)

    def propose_config_change(
        self, current_config: Dict[str, Any], aggregated_deltas: Dict[str, Any]
    ) -> Dict[str, Any]:
        return self._fallback.propose_config_change(current_config, aggregated_deltas)
