"""Tests for LLMClient (provider-agnostic via httpx).

Mock httpx responses to avoid network during CI.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from core.shared.rag.exceptions import LLMError
from core.shared.rag.llm_client import LLMClient, LLMConfig


class TestLLMConfig:
    def test_anthropic_default_base_url(self):
        cfg = LLMConfig(provider="anthropic", api_key="sk-test", model="claude-sonnet-4-6")
        assert "anthropic.com" in cfg.base_url

    def test_openai_default_base_url(self):
        cfg = LLMConfig(provider="openai", api_key="sk-test", model="gpt-4o")
        assert "openai.com" in cfg.base_url

    def test_openrouter_default_base_url(self):
        cfg = LLMConfig(provider="openrouter", api_key="sk-or-test", model="meta-llama/llama-3.3-70b")
        assert "openrouter.ai" in cfg.base_url

    def test_ollama_default_base_url(self):
        cfg = LLMConfig(provider="ollama", model="mistral-small")
        assert "localhost:11434" in cfg.base_url

    def test_explicit_base_url_overrides_default(self):
        cfg = LLMConfig(
            provider="openai",
            base_url="https://custom.example.com/v1",
            api_key="sk-test",
            model="gpt-4o",
        )
        assert cfg.base_url == "https://custom.example.com/v1"

    def test_unknown_provider_raises(self):
        with pytest.raises(LLMError):
            LLMConfig(provider="bogus", api_key="x", model="x")


class TestComplete:
    @pytest.fixture
    def anthropic_response(self):
        return {
            "content": [{"type": "text", "text": "Risposta sintetica generata."}],
            "model": "claude-sonnet-4-6",
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 50, "output_tokens": 10},
        }

    @pytest.fixture
    def openai_response(self):
        return {
            "choices": [
                {
                    "message": {"role": "assistant", "content": "Risposta sintetica generata."},
                    "finish_reason": "stop",
                }
            ],
            "model": "gpt-4o",
        }

    def test_anthropic_complete(self, anthropic_response):
        cfg = LLMConfig(provider="anthropic", api_key="sk-test", model="claude-sonnet-4-6")
        client = LLMClient(cfg)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = anthropic_response
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.post", return_value=mock_response):
            text = client.complete("system", "user prompt", max_tokens=100)
        assert text == "Risposta sintetica generata."

    def test_openai_complete(self, openai_response):
        cfg = LLMConfig(provider="openai", api_key="sk-test", model="gpt-4o")
        client = LLMClient(cfg)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = openai_response
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.post", return_value=mock_response):
            text = client.complete("system", "user prompt")
        assert text == "Risposta sintetica generata."

    def test_openrouter_uses_openai_format(self, openai_response):
        cfg = LLMConfig(provider="openrouter", api_key="sk-or-test", model="x/y")
        client = LLMClient(cfg)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = openai_response
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.post", return_value=mock_response):
            text = client.complete("system", "user prompt")
        assert text == "Risposta sintetica generata."

    def test_ollama_uses_openai_compat_endpoint(self, openai_response):
        cfg = LLMConfig(provider="ollama", model="mistral-small")
        client = LLMClient(cfg)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = openai_response
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.post", return_value=mock_response) as mp:
            text = client.complete("system", "user prompt")
        assert text == "Risposta sintetica generata."
        url_arg = mp.call_args[0][0]
        assert "/v1/chat/completions" in url_arg


class TestErrorHandling:
    def test_http_error_wrapped_as_llm_error(self):
        cfg = LLMConfig(provider="openai", api_key="sk-test", model="gpt-4o")
        client = LLMClient(cfg)

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "401 Unauthorized",
            request=MagicMock(),
            response=mock_response,
        )

        with patch("httpx.post", return_value=mock_response):
            with pytest.raises(LLMError) as excinfo:
                client.complete("system", "user")
        assert "401" in str(excinfo.value) or "Unauthorized" in str(excinfo.value)

    def test_network_error_wrapped(self):
        cfg = LLMConfig(provider="openai", api_key="sk-test", model="gpt-4o")
        client = LLMClient(cfg)

        with patch("httpx.post", side_effect=httpx.ConnectError("connection refused")):
            with pytest.raises(LLMError) as excinfo:
                client.complete("system", "user")
        assert "connection" in str(excinfo.value).lower()

    def test_malformed_response_wrapped(self):
        cfg = LLMConfig(provider="openai", api_key="sk-test", model="gpt-4o")
        client = LLMClient(cfg)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"unexpected": "shape"}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.post", return_value=mock_response):
            with pytest.raises(LLMError):
                client.complete("system", "user")


class TestHeaders:
    def test_anthropic_sends_x_api_key_header(self):
        cfg = LLMConfig(provider="anthropic", api_key="sk-ant-test", model="claude-sonnet-4-6")
        client = LLMClient(cfg)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "content": [{"type": "text", "text": "x"}],
            "stop_reason": "end_turn",
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.post", return_value=mock_response) as mp:
            client.complete("system", "user")
        headers = mp.call_args[1]["headers"]
        assert headers.get("x-api-key") == "sk-ant-test"
        assert "anthropic-version" in headers

    def test_openai_sends_bearer_header(self):
        cfg = LLMConfig(provider="openai", api_key="sk-test", model="gpt-4o")
        client = LLMClient(cfg)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "x"}, "finish_reason": "stop"}]
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.post", return_value=mock_response) as mp:
            client.complete("system", "user")
        headers = mp.call_args[1]["headers"]
        assert headers.get("Authorization") == "Bearer sk-test"
