"""Test per core/llm.py (factory client Anthropic alimentato da BYOK)."""

from __future__ import annotations

import pytest

from core import llm
from core.shared.rag.exceptions import LLMError
from core.shared.rag.llm_client import LLMClient


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    # niente ~/.anthropic/credentials reale durante i test
    monkeypatch.setenv("HOME", str(tmp_path))
    yield


class TestResolveKey:
    def test_none_when_no_source(self, monkeypatch):
        monkeypatch.setattr("core.system._read_byok_key", lambda: None)
        assert llm.resolve_anthropic_key() is None

    def test_byok_takes_priority(self, monkeypatch):
        monkeypatch.setattr("core.system._read_byok_key", lambda: "sk-ant-byok")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-env")
        assert llm.resolve_anthropic_key() == "sk-ant-byok"

    def test_env_fallback(self, monkeypatch):
        monkeypatch.setattr("core.system._read_byok_key", lambda: None)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-env")
        assert llm.resolve_anthropic_key() == "sk-ant-env"

    def test_sdk_creds(self, monkeypatch, tmp_path):
        monkeypatch.setattr("core.system._read_byok_key", lambda: None)
        creds = tmp_path / ".anthropic"
        creds.mkdir()
        (creds / "credentials").write_text('{"api_key": "sk-ant-sdk"}', encoding="utf-8")
        assert llm.resolve_anthropic_key() == "sk-ant-sdk"


class TestClient:
    def test_raises_without_key(self, monkeypatch):
        monkeypatch.setattr(llm, "resolve_anthropic_key", lambda: None)
        with pytest.raises(LLMError):
            llm.anthropic_client()

    def test_builds_anthropic_client(self, monkeypatch):
        monkeypatch.setattr(llm, "resolve_anthropic_key", lambda: "sk-ant-xyz")
        client = llm.anthropic_client(model="claude-haiku-4-5-20251001")
        assert isinstance(client, LLMClient)
        assert client.config.provider == "anthropic"
        assert client.config.api_key == "sk-ant-xyz"
        assert client.config.model == "claude-haiku-4-5-20251001"
