"""LLM client OpenAI-compatible swappabile (Anthropic / OpenAI / OpenRouter / Ollama).

Supportati:
- `anthropic`: API nativa Claude (https://api.anthropic.com/v1/messages)
- `openai`: API OpenAI (https://api.openai.com/v1/chat/completions)
- `openrouter`: gateway multi-modello OpenAI-compat (https://openrouter.ai/api/v1)
- `ollama`: server locale OpenAI-compat (http://localhost:11434/v1)

Anthropic ha API nativa differente; per gli altri si usa OpenAI chat-completions.
Tutti gli errori uniformati in `LLMError`.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass, field

import httpx

from core.shared.rag.exceptions import LLMError


_KNOWN_PROVIDERS = ("anthropic", "openai", "openrouter", "ollama")

_DEFAULT_BASE_URLS: dict[str, str] = {
    "anthropic": "https://api.anthropic.com/v1",
    "openai": "https://api.openai.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "ollama": "http://localhost:11434/v1",
}

_ANTHROPIC_VERSION = "2023-06-01"
_CONTENT_TYPE_JSON = "application/json"


@dataclass
class LLMConfig:
    provider: str
    model: str
    api_key: str | None = None
    base_url: str = field(default="")

    def __post_init__(self) -> None:
        if self.provider not in _KNOWN_PROVIDERS:
            raise LLMError(
                f"unknown provider: {self.provider}. "
                f"Supported: {', '.join(_KNOWN_PROVIDERS)}"
            )
        if not self.base_url:
            self.base_url = _DEFAULT_BASE_URLS[self.provider]


class LLMClient:
    def __init__(self, config: LLMConfig) -> None:
        self.config = config

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 2000,
    ) -> str:
        if self.config.provider == "anthropic":
            return self._complete_anthropic(
                system_prompt, user_prompt, temperature, max_tokens
            )
        return self._complete_openai_compat(
            system_prompt, user_prompt, temperature, max_tokens
        )

    def stream_complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 2000,
    ) -> Iterator[str]:
        if self.config.provider == "anthropic":
            yield from self._stream_anthropic(
                system_prompt, user_prompt, temperature, max_tokens
            )
        else:
            yield from self._stream_openai_compat(
                system_prompt, user_prompt, temperature, max_tokens
            )

    def _complete_anthropic(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        url = f"{self.config.base_url}/messages"
        headers = {
            "x-api-key": self.config.api_key or "",
            "anthropic-version": _ANTHROPIC_VERSION,
            "content-type": _CONTENT_TYPE_JSON,
        }
        payload = {
            "model": self.config.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        }
        data = self._post(url, payload, headers)
        try:
            content = data["content"]
            if not content or not isinstance(content, list):
                raise KeyError("content")
            first = content[0]
            text = first.get("text") if isinstance(first, dict) else None
            if not text:
                raise KeyError("text")
            return text
        except (KeyError, TypeError, IndexError) as exc:
            raise LLMError(
                f"unexpected anthropic response shape: {exc}"
            ) from exc

    def _stream_anthropic(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> Iterator[str]:
        url = f"{self.config.base_url}/messages"
        headers = {
            "x-api-key": self.config.api_key or "",
            "anthropic-version": _ANTHROPIC_VERSION,
            "content-type": _CONTENT_TYPE_JSON,
        }
        payload = {
            "model": self.config.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
            "stream": True,
        }
        yield from self._stream_sse_anthropic(url, payload, headers)

    def _complete_openai_compat(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        url = f"{self.config.base_url}/chat/completions"
        headers = {"content-type": _CONTENT_TYPE_JSON}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        data = self._post(url, payload, headers)
        try:
            choices = data["choices"]
            if not choices:
                raise KeyError("choices")
            msg = choices[0].get("message", {})
            content = msg.get("content")
            if content is None:
                raise KeyError("content")
            return content
        except (KeyError, TypeError, IndexError) as exc:
            raise LLMError(
                f"unexpected openai-compat response shape: {exc}"
            ) from exc

    def _stream_openai_compat(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> Iterator[str]:
        url = f"{self.config.base_url}/chat/completions"
        headers = {"content-type": _CONTENT_TYPE_JSON}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        yield from self._stream_sse_openai(url, payload, headers)

    def _post(self, url: str, payload: dict, headers: dict) -> dict:
        try:
            response = httpx.post(
                url,
                json=payload,
                headers=headers,
                timeout=120.0,
            )
        except httpx.ConnectError as exc:
            raise LLMError(f"connection failed: {exc}") from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"http error: {exc}") from exc

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            body = ""
            try:
                body = response.text[:500]
            except Exception:
                pass
            raise LLMError(
                f"HTTP {response.status_code}: {exc}. body: {body}"
            ) from exc

        return response.json()

    def _stream_sse_openai(
        self, url: str, payload: dict, headers: dict
    ) -> Iterator[str]:
        try:
            with httpx.stream(
                "POST", url, json=payload, headers=headers, timeout=300.0
            ) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data_str = line[5:].strip()
                    if data_str == "[DONE]":
                        return
                    try:
                        chunk = json.loads(data_str)
                        delta = chunk["choices"][0].get("delta", {})
                        content = delta.get("content")
                        if content:
                            yield content
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue
        except (httpx.HTTPError, httpx.ConnectError) as exc:
            raise LLMError(f"stream error: {exc}") from exc

    def _stream_sse_anthropic(
        self, url: str, payload: dict, headers: dict
    ) -> Iterator[str]:
        try:
            with httpx.stream(
                "POST", url, json=payload, headers=headers, timeout=300.0
            ) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data_str = line[5:].strip()
                    try:
                        event = json.loads(data_str)
                        if event.get("type") == "content_block_delta":
                            delta = event.get("delta", {})
                            text = delta.get("text")
                            if text:
                                yield text
                    except (json.JSONDecodeError, KeyError):
                        continue
        except (httpx.HTTPError, httpx.ConnectError) as exc:
            raise LLMError(f"stream error: {exc}") from exc
