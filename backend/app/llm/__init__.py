"""Pluggable LLM layer.

Every call site imports `get_provider()` and never a concrete class — swapping
providers is a one-line change (`LLM_PROVIDER` in .env). Every provider's
output that will be persisted or executed is validated/repaired downstream
(app/config_schema.py); the LLM is never trusted blindly, per the core law
that it authors config and advises on breaks but never matches at run-time.
"""
from __future__ import annotations

from functools import lru_cache

from ..config import get_settings
from .base import LLMProvider
from .stub import StubProvider


@lru_cache
def get_provider() -> LLMProvider:
    settings = get_settings()
    provider = (settings.llm_provider or "stub").lower()

    if provider == "stub":
        return StubProvider()

    if provider == "gemini":
        from .gemini import GeminiProvider

        if not settings.gemini_api_key:
            return StubProvider()
        return GeminiProvider(api_key=settings.gemini_api_key, model=settings.llm_model)

    if provider == "openai":
        from .openai_compat import OpenAIProvider

        if not settings.openai_api_key:
            return StubProvider()
        return OpenAIProvider(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            model=settings.llm_model,
        )

    # Unknown provider name: never crash the app over a config typo — degrade
    # to the deterministic stub, same posture as "LLM authoring flaky" below.
    return StubProvider()


__all__ = ["get_provider", "LLMProvider"]
