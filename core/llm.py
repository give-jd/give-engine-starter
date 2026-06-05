"""Factory engine-side per un client LLM Anthropic alimentato dalla chiave BYOK.

Non modifica il modulo condiviso `core/shared/rag/`: riusa il suo `LLMClient`
pubblico passando la chiave risolta dalle fonti locali. La chiave non lascia mai
la macchina dell'utente (Punto Cardine 14).

Priorità di risoluzione (allineata a `ai_environment._check_anthropic_key`):
1. BYOK locale   → ~/.givengine/credentials.json  (campo `anthropic_api_key`)
2. SDK Anthropic → ~/.anthropic/credentials        (best-effort, formato JSON)
3. Variabile env → ANTHROPIC_API_KEY
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from core.shared.rag.exceptions import LLMError
from core.shared.rag.llm_client import LLMClient, LLMConfig

# Default economico per validazione e usi leggeri.
DEFAULT_ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"


def _key_from_sdk_creds() -> str | None:
    sdk = Path(os.path.expanduser("~/.anthropic/credentials"))
    try:
        if not (sdk.exists() and sdk.stat().st_size > 0):
            return None
        data = json.loads(sdk.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    for field in ("api_key", "anthropic_api_key", "ANTHROPIC_API_KEY"):
        value = data.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def resolve_anthropic_key() -> str | None:
    """Risolve la chiave Anthropic dalle fonti locali, in ordine di priorità.

    Returns:
        La chiave in chiaro, oppure None se nessuna fonte la fornisce.
    """
    from core import system as _sys

    key = _sys._read_byok_key()
    if key:
        return key

    key = _key_from_sdk_creds()
    if key:
        return key

    env = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    return env or None


def anthropic_client(model: str = DEFAULT_ANTHROPIC_MODEL) -> LLMClient:
    """Costruisce un `LLMClient` Anthropic con la chiave BYOK risolta.

    Args:
        model: id modello Anthropic da usare.

    Returns:
        Un `LLMClient` pronto per `.complete()` / `.stream_complete()`.

    Raises:
        LLMError: se nessuna chiave API Anthropic è configurata.
    """
    key = resolve_anthropic_key()
    if not key:
        raise LLMError("nessuna chiave API Anthropic configurata (BYOK)")
    return LLMClient(LLMConfig(provider="anthropic", model=model, api_key=key))
