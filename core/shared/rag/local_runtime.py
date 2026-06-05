"""Readiness e GPU detect per LLM locale (provider Ollama).

Layer di prontezza attorno al provider `ollama` di `llm_client.py`.
Non esegue inferenza: risponde se Ollama è acceso, se il modello è
scaricato, e se gira su GPU — prima che atheneo-light chiami
`LLMClient.complete()`.

Invariante hard no-cloud (Punto 14): accetta SOLO host loopback
(`localhost` / `127.0.0.1` / `::1`). Un base_url remoto solleva
`LocalRuntimeError`, così è impossibile che il runtime "locale" parli a
un host remoto per misconfig.

GPU detection via endpoint nativo Ollama `/api/ps` (`size_vram > 0` =
GPU attiva). Nessuna dipendenza nuova oltre a `httpx`.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from core.shared.rag.exceptions import LLMError

_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
_DEFAULT_TIMEOUT = 3.0


class LocalRuntimeError(LLMError):
    """Errore del runtime locale (Ollama spento, modello assente, host non locale).

    Sottoclasse di `LLMError` così i chiamanti esistenti (es. atheneo-light
    `synthesize`) la catturano col `except LLMError` già in essere.
    """


@dataclass(frozen=True)
class RuntimeStatus:
    """Stato del runtime locale, per badge informativo UI.

    Attributes:
        ollama_running: server Ollama raggiungibile su host loopback.
        models_available: nomi modelli scaricati localmente.
        requested_model: modello richiesto (None se solo probe informativo).
        model_present: requested_model è tra models_available.
        gpu_active: True se un modello caricato usa VRAM; None se ignoto
            (nessun modello caricato in /api/ps).
        vram_bytes: VRAM totale usata dai modelli caricati; None se ignoto.
    """

    ollama_running: bool
    models_available: tuple[str, ...]
    requested_model: str | None
    model_present: bool
    gpu_active: bool | None
    vram_bytes: int | None


def _assert_loopback(base_url: str) -> None:
    """Solleva LocalRuntimeError se base_url non punta a un host loopback.

    Args:
        base_url: URL del runtime (es. http://localhost:11434/v1).

    Raises:
        LocalRuntimeError: host non in {localhost, 127.0.0.1, ::1}.
    """
    host = urlparse(base_url).hostname
    if host not in _LOOPBACK_HOSTS:
        raise LocalRuntimeError(
            f"Runtime locale ammette solo host locale, ricevuto: {host}. "
            "Vincolo no-cloud (Punto 14)."
        )


def _native_root(base_url: str) -> str:
    """Converte il base_url OpenAI-compat nella root nativa Ollama.

    Gli endpoint `/api/*` di Ollama non stanno sotto `/v1`.
    Es. http://localhost:11434/v1 → http://localhost:11434.
    """
    root = base_url.rstrip("/")
    if root.endswith("/v1"):
        root = root[: -len("/v1")]
    return root.rstrip("/")


def check_ollama(base_url: str, timeout: float = _DEFAULT_TIMEOUT) -> bool:
    """True se il server Ollama risponde su /api/version.

    Errori di connessione/HTTP → False (non solleva).
    """
    root = _native_root(base_url)
    try:
        resp = httpx.get(f"{root}/api/version", timeout=timeout)
    except httpx.HTTPError:
        return False
    return resp.status_code == 200


def list_local_models(
    base_url: str, timeout: float = _DEFAULT_TIMEOUT
) -> tuple[str, ...]:
    """Nomi dei modelli scaricati localmente (da /api/tags).

    Errori di connessione → tupla vuota (non solleva).
    """
    root = _native_root(base_url)
    try:
        resp = httpx.get(f"{root}/api/tags", timeout=timeout)
    except httpx.HTTPError:
        return ()
    models = resp.json().get("models", [])
    return tuple(m["name"] for m in models if "name" in m)


def gpu_status(
    base_url: str, timeout: float = _DEFAULT_TIMEOUT
) -> tuple[bool | None, int | None]:
    """Stato GPU dai modelli caricati (da /api/ps).

    Returns:
        (gpu_active, vram_bytes). Nessun modello caricato o errore →
        (None, None). Modello caricato → (size_vram > 0, size_vram).
    """
    root = _native_root(base_url)
    try:
        resp = httpx.get(f"{root}/api/ps", timeout=timeout)
    except httpx.HTTPError:
        return (None, None)
    models = resp.json().get("models", [])
    if not models:
        return (None, None)
    vram = sum(int(m.get("size_vram", 0)) for m in models)
    return (vram > 0, vram)


def runtime_status(
    base_url: str,
    model: str | None = None,
    *,
    timeout: float = _DEFAULT_TIMEOUT,
) -> RuntimeStatus:
    """Aggrega lo stato del runtime locale (path informativo per UI).

    Non solleva per "non pronto" (campi a False/None); solleva solo per
    violazione del vincolo loopback.

    Raises:
        LocalRuntimeError: base_url non loopback.
    """
    _assert_loopback(base_url)
    running = check_ollama(base_url, timeout)
    models = list_local_models(base_url, timeout) if running else ()
    gpu_active, vram = gpu_status(base_url, timeout) if running else (None, None)
    return RuntimeStatus(
        ollama_running=running,
        models_available=models,
        requested_model=model,
        model_present=model in models if model is not None else False,
        gpu_active=gpu_active,
        vram_bytes=vram,
    )


def require_ready(
    base_url: str, model: str, *, timeout: float = _DEFAULT_TIMEOUT
) -> None:
    """Gating pre-complete(): solleva con messaggio IT se non pronto.

    Args:
        base_url: URL runtime locale (deve essere loopback).
        model: modello che deve essere scaricato.

    Raises:
        LocalRuntimeError: host non locale, Ollama spento, o modello assente.
            Messaggio in italiano azionabile.
    """
    _assert_loopback(base_url)
    if not check_ollama(base_url, timeout):
        raise LocalRuntimeError(
            f"Ollama non in esecuzione su {_native_root(base_url)}. "
            "Avvialo con: ollama serve"
        )
    if model not in list_local_models(base_url, timeout):
        raise LocalRuntimeError(
            f"Modello '{model}' non scaricato. Scaricalo con: ollama pull {model}"
        )
