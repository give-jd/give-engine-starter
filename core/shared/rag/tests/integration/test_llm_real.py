"""Real LLM integration test scaffolding.

Skippato di default. Esegue chiamata reale a un provider configurato via env:

- `ANTHROPIC_API_KEY`     → test Anthropic
- `OPENAI_API_KEY`        → test OpenAI
- `OPENROUTER_API_KEY`    → test OpenRouter
- `OLLAMA_URL` + `OLLAMA_MODEL` → test Ollama locale

Almeno un provider deve essere configurato; altrimenti skip.

Eseguire con:
    RAG_RUN_SLOW_TESTS=1 ANTHROPIC_API_KEY=sk-ant-... \\
      pytest core/shared/rag/tests/integration/test_llm_real.py
"""

from __future__ import annotations

import os

import pytest

from core.shared.rag.exceptions import LLMError
from core.shared.rag.llm_client import LLMClient, LLMConfig


def _has_any_provider() -> bool:
    return any(
        os.environ.get(k)
        for k in (
            "ANTHROPIC_API_KEY",
            "OPENAI_API_KEY",
            "OPENROUTER_API_KEY",
            "OLLAMA_URL",
        )
    )


pytestmark = pytest.mark.skipif(
    os.environ.get("RAG_RUN_SLOW_TESTS") != "1" or not _has_any_provider(),
    reason="slow integration test (richiede RAG_RUN_SLOW_TESTS=1 + provider env)",
)


def _configs_to_test() -> list[LLMConfig]:
    configs: list[LLMConfig] = []
    if os.environ.get("ANTHROPIC_API_KEY"):
        configs.append(
            LLMConfig(
                provider="anthropic",
                api_key=os.environ["ANTHROPIC_API_KEY"],
                model=os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001"),
            )
        )
    if os.environ.get("OPENAI_API_KEY"):
        configs.append(
            LLMConfig(
                provider="openai",
                api_key=os.environ["OPENAI_API_KEY"],
                model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            )
        )
    if os.environ.get("OPENROUTER_API_KEY"):
        configs.append(
            LLMConfig(
                provider="openrouter",
                api_key=os.environ["OPENROUTER_API_KEY"],
                model=os.environ.get(
                    "OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct"
                ),
            )
        )
    if os.environ.get("OLLAMA_URL"):
        configs.append(
            LLMConfig(
                provider="ollama",
                base_url=os.environ["OLLAMA_URL"],
                model=os.environ.get("OLLAMA_MODEL", "mistral-small"),
            )
        )
    return configs


class TestLLMReal:
    @pytest.mark.parametrize("config", _configs_to_test())
    def test_provider_complete_returns_non_empty_response(
        self, config: LLMConfig
    ):
        client = LLMClient(config)
        try:
            response = client.complete(
                system_prompt=(
                    "Rispondi in italiano con una sola parola: SI o NO. Niente altro."
                ),
                user_prompt="L'acqua bolle a 100 gradi Celsius a livello del mare?",
                temperature=0.0,
                max_tokens=10,
            )
        except LLMError as exc:
            pytest.fail(
                f"provider {config.provider}/{config.model} fallito: {exc}"
            )
        assert response.strip(), (
            f"provider {config.provider} ha restituito risposta vuota"
        )
        assert any(
            token in response.lower() for token in ("si", "sì", "yes")
        ), f"provider {config.provider} risposta inattesa: {response!r}"

    @pytest.mark.parametrize("config", _configs_to_test())
    def test_provider_handles_citation_pattern(self, config: LLMConfig):
        client = LLMClient(config)
        try:
            response = client.complete(
                system_prompt=(
                    "Cita SEMPRE la fonte nel formato [chunk N]. Niente altro."
                ),
                user_prompt=(
                    "Fonte: [chunk 1] L'acqua bolle a 100 gradi C.\n\n"
                    "Domanda: a che temperatura bolle l'acqua? Rispondi citando la fonte."
                ),
                temperature=0.0,
                max_tokens=50,
            )
        except LLMError as exc:
            pytest.fail(f"provider {config.provider} fallito: {exc}")
        assert (
            "[chunk 1]" in response.lower()
            or "[chunk1]" in response.lower()
            or "chunk 1" in response.lower()
        ), f"provider {config.provider} non ha citato chunk: {response!r}"
