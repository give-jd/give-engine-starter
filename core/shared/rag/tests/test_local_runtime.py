"""Tests for local_runtime (Ollama readiness + GPU detect).

Mock httpx.get to avoid network during CI. No real Ollama required.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from core.shared.rag.exceptions import LLMError
from core.shared.rag.local_runtime import (
    LocalRuntimeError,
    RuntimeStatus,
    _assert_loopback,
    _native_root,
    check_ollama,
    gpu_status,
    list_local_models,
    require_ready,
    runtime_status,
)


def _resp(payload: dict, status: int = 200) -> MagicMock:
    r = MagicMock()
    r.status_code = status
    r.json.return_value = payload
    return r


def _router(routes: dict[str, MagicMock]):
    """Return a fake httpx.get dispatching by URL suffix (/api/...)."""

    def _get(url: str, *args, **kwargs):
        for suffix, resp in routes.items():
            if url.endswith(suffix):
                if isinstance(resp, Exception):
                    raise resp
                return resp
        raise AssertionError(f"unexpected url: {url}")

    return _get


class TestAssertLoopback:
    @pytest.mark.parametrize(
        "base_url",
        [
            "http://localhost:11434/v1",
            "http://127.0.0.1:11434/v1",
            "http://[::1]:11434/v1",
        ],
    )
    def test_accepts_loopback(self, base_url):
        _assert_loopback(base_url)  # no raise

    @pytest.mark.parametrize(
        "base_url",
        [
            "http://ollama.example.com:11434/v1",
            "http://10.0.0.5:11434/v1",
            "https://api.openai.com/v1",
        ],
    )
    def test_rejects_non_loopback(self, base_url):
        with pytest.raises(LocalRuntimeError) as exc:
            _assert_loopback(base_url)
        assert "no-cloud" in str(exc.value).lower()

    def test_localruntimeerror_is_llmerror(self):
        # caller catches with existing `except LLMError`
        assert issubclass(LocalRuntimeError, LLMError)


class TestNativeRoot:
    def test_strips_v1(self):
        assert _native_root("http://localhost:11434/v1") == "http://localhost:11434"

    def test_strips_trailing_slash(self):
        assert _native_root("http://localhost:11434/v1/") == "http://localhost:11434"

    def test_idempotent_when_already_root(self):
        assert _native_root("http://localhost:11434") == "http://localhost:11434"


class TestCheckOllama:
    def test_running(self):
        with patch("httpx.get", return_value=_resp({"version": "0.5.0"})):
            assert check_ollama("http://localhost:11434/v1") is True

    def test_down_connection_error(self):
        with patch("httpx.get", side_effect=httpx.ConnectError("refused")):
            assert check_ollama("http://localhost:11434/v1") is False


class TestListLocalModels:
    def test_empty(self):
        with patch("httpx.get", return_value=_resp({"models": []})):
            assert list_local_models("http://localhost:11434/v1") == ()

    def test_populated(self):
        payload = {"models": [{"name": "llama3:8b"}, {"name": "mistral-small"}]}
        with patch("httpx.get", return_value=_resp(payload)):
            assert list_local_models("http://localhost:11434/v1") == (
                "llama3:8b",
                "mistral-small",
            )

    def test_connection_error_returns_empty(self):
        with patch("httpx.get", side_effect=httpx.ConnectError("refused")):
            assert list_local_models("http://localhost:11434/v1") == ()


class TestGpuStatus:
    def test_gpu_active(self):
        payload = {"models": [{"name": "llama3:8b", "size_vram": 5_000_000_000}]}
        with patch("httpx.get", return_value=_resp(payload)):
            active, vram = gpu_status("http://localhost:11434/v1")
        assert active is True
        assert vram == 5_000_000_000

    def test_cpu_only_zero_vram(self):
        payload = {"models": [{"name": "llama3:8b", "size_vram": 0}]}
        with patch("httpx.get", return_value=_resp(payload)):
            active, vram = gpu_status("http://localhost:11434/v1")
        assert active is False
        assert vram == 0

    def test_no_model_loaded_unknown(self):
        with patch("httpx.get", return_value=_resp({"models": []})):
            active, vram = gpu_status("http://localhost:11434/v1")
        assert active is None
        assert vram is None

    def test_connection_error_unknown(self):
        with patch("httpx.get", side_effect=httpx.ConnectError("refused")):
            active, vram = gpu_status("http://localhost:11434/v1")
        assert active is None
        assert vram is None


class TestRuntimeStatus:
    def test_aggregates_ready_with_gpu(self):
        routes = {
            "/api/version": _resp({"version": "0.5.0"}),
            "/api/tags": _resp({"models": [{"name": "llama3:8b"}]}),
            "/api/ps": _resp(
                {"models": [{"name": "llama3:8b", "size_vram": 5_000_000_000}]}
            ),
        }
        with patch("httpx.get", side_effect=_router(routes)):
            st = runtime_status("http://localhost:11434/v1", model="llama3:8b")
        assert isinstance(st, RuntimeStatus)
        assert st.ollama_running is True
        assert st.models_available == ("llama3:8b",)
        assert st.requested_model == "llama3:8b"
        assert st.model_present is True
        assert st.gpu_active is True
        assert st.vram_bytes == 5_000_000_000

    def test_not_ready_does_not_raise(self):
        with patch("httpx.get", side_effect=httpx.ConnectError("refused")):
            st = runtime_status("http://localhost:11434/v1", model="llama3:8b")
        assert st.ollama_running is False
        assert st.model_present is False
        assert st.gpu_active is None

    def test_non_loopback_raises(self):
        with pytest.raises(LocalRuntimeError):
            runtime_status("http://10.0.0.5:11434/v1", model="llama3:8b")


class TestRequireReady:
    def test_happy_path_returns_none(self):
        routes = {
            "/api/version": _resp({"version": "0.5.0"}),
            "/api/tags": _resp({"models": [{"name": "llama3:8b"}]}),
        }
        with patch("httpx.get", side_effect=_router(routes)):
            assert require_ready("http://localhost:11434/v1", "llama3:8b") is None

    def test_ollama_down_raises_it(self):
        with patch("httpx.get", side_effect=httpx.ConnectError("refused")):
            with pytest.raises(LocalRuntimeError) as exc:
                require_ready("http://localhost:11434/v1", "llama3:8b")
        assert "ollama serve" in str(exc.value).lower()

    def test_model_absent_raises_it(self):
        routes = {
            "/api/version": _resp({"version": "0.5.0"}),
            "/api/tags": _resp({"models": [{"name": "mistral-small"}]}),
        }
        with patch("httpx.get", side_effect=_router(routes)):
            with pytest.raises(LocalRuntimeError) as exc:
                require_ready("http://localhost:11434/v1", "llama3:8b")
        assert "ollama pull llama3:8b" in str(exc.value).lower()

    def test_non_loopback_raises(self):
        with pytest.raises(LocalRuntimeError):
            require_ready("https://api.openai.com/v1", "llama3:8b")
