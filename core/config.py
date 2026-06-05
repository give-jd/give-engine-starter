"""Centralized env loading for Gi.Ve Engine.

Every module that needs LEMONSQUEEZY_* env vars must import from this
module - never from `os.environ` directly at module scope. That keeps the
load path single-source and ensures local `.env.test` is picked up before
any consumer reads its variables.

On Vercel (production / preview deploys) the env file does not exist; the
Project Settings env vars are already in `os.environ`, so we silently skip
the dotenv load.
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:                                # graceful: dotenv is optional in prod
    def load_dotenv(*_args, **_kwargs) -> bool:    # type: ignore[no-redef]
        return False


MODE = os.getenv("LEMONSQUEEZY_MODE", "test")
ENV_FILE = Path(__file__).resolve().parents[1] / f".env.{MODE}"
if ENV_FILE.exists():
    load_dotenv(ENV_FILE, override=False)
# else: in produzione Vercel le var vengono da Project Settings


def get(name: str, default: str = "") -> str:
    """Read an env var (works on both local + Vercel deploys)."""
    return os.getenv(name, default)


def is_configured() -> bool:
    """True iff the minimum Lemon Squeezy env set is present."""
    return all(get(k) for k in (
        "LEMONSQUEEZY_WEBHOOK_SECRET",
        "LEMONSQUEEZY_API_KEY",
        "LEMONSQUEEZY_STORE_ID",
    ))


def variant_to_tier_map() -> dict[str, str]:
    """{variant_id_str: 'starter'|'catalog'|'all-access'} from env."""
    out: dict[str, str] = {}
    starter = get("LEMONSQUEEZY_VARIANT_ID_STARTER")
    catalog = get("LEMONSQUEEZY_VARIANT_ID_CATALOG")
    allaccess = get("LEMONSQUEEZY_VARIANT_ID_ALLACCESS")
    if starter:
        out[starter] = "starter"
    if catalog:
        out[catalog] = "catalog"
    if allaccess:
        out[allaccess] = "all-access"
    return out


def is_test_mode() -> bool:
    return MODE == "test"


# ---------- Mode detection (single source of truth) ------------------------
# The mode (test|live) is DETERMINED by calling the Lemon Squeezy API.
# Env var LEMONSQUEEZY_MODE exists only as a consistency check: if it
# diverges from the detected real mode, the webhook returns 503 and the
# health check surfaces the mismatch.
#
# Cached for the lifetime of the cold start (Vercel function instance).
# A new cold start triggers a fresh detection.

_DETECTED_MODE: str | None = None
_DETECTION_ERROR: str | None = None


def _fetch_lemonsqueezy_mode() -> tuple[str | None, str | None]:
    """GET https://api.lemonsqueezy.com/v1/products?page[size]=1, return
    ('test'|'live', None) on success or (None, error_msg) on failure.

    NB: /v1/users/me and /v1/stores do NOT expose test_mode.
    /v1/products carries it on each product.
    """
    api_key = get("LEMONSQUEEZY_API_KEY")
    if not api_key:
        return None, "missing LEMONSQUEEZY_API_KEY"
    try:
        import httpx  # type: ignore
        with httpx.Client(timeout=8.0) as client:
            r = client.get(
                "https://api.lemonsqueezy.com/v1/products",
                params={"page[size]": "1"},
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Accept": "application/vnd.api+json",
                },
            )
        if r.status_code != 200:
            return None, f"LS API HTTP {r.status_code}"
        payload = r.json()
        items = payload.get("data") or []
        if not items:
            return None, "no products returned (create at least one product in LS)"
        attrs = items[0].get("attributes") or {}
        if "test_mode" not in attrs:
            return None, "LS API response missing data[0].attributes.test_mode"
        return ("test" if bool(attrs["test_mode"]) else "live"), None
    except Exception as e:                                # pragma: no cover
        return None, f"LS API error: {type(e).__name__}: {e}"


def detected_mode() -> str:
    """Real mode as detected from the LS API key. Cached per cold start.

    On detection failure, falls back to the declared LEMONSQUEEZY_MODE
    env var (so a transient network error doesn't block webhook ingestion).
    The error reason is preserved in _DETECTION_ERROR for health visibility.
    """
    global _DETECTED_MODE, _DETECTION_ERROR
    if _DETECTED_MODE is not None:
        return _DETECTED_MODE
    mode, err = _fetch_lemonsqueezy_mode()
    if mode is None:
        _DETECTION_ERROR = err
        _DETECTED_MODE = MODE  # fallback to declared
    else:
        _DETECTION_ERROR = None
        _DETECTED_MODE = mode
    return _DETECTED_MODE


def detection_error() -> str | None:
    """Last detection error (None on success). Triggers detection if cold."""
    detected_mode()
    return _DETECTION_ERROR


def key_mode_match() -> bool:
    """True iff declared MODE matches detected (or detection failed —
    in which case we cannot prove mismatch, so we don't block traffic)."""
    if _DETECTION_ERROR is not None:
        return True
    return MODE == detected_mode()


def health_checks() -> dict:
    """Per-flag snapshot for the webhook GET health endpoint."""
    detected_mode()  # warm cache
    return {
        "webhook_secret_present": bool(get("LEMONSQUEEZY_WEBHOOK_SECRET")),
        "api_key_present": bool(get("LEMONSQUEEZY_API_KEY")),
        "api_key_valid": _DETECTION_ERROR is None and _DETECTED_MODE is not None,
        "checkout_url_catalog_present": bool(get("LEMONSQUEEZY_CHECKOUT_URL_CATALOG")),
        "checkout_url_allaccess_present": bool(get("LEMONSQUEEZY_CHECKOUT_URL_ALLACCESS")),
        "variant_id_catalog_present": bool(get("LEMONSQUEEZY_VARIANT_ID_CATALOG")),
        "variant_id_allaccess_present": bool(get("LEMONSQUEEZY_VARIANT_ID_ALLACCESS")),
        "key_mode_match": key_mode_match(),
    }


def _reset_detection_cache() -> None:
    """Test-only: clear cache so next detected_mode() re-fetches."""
    global _DETECTED_MODE, _DETECTION_ERROR
    _DETECTED_MODE = None
    _DETECTION_ERROR = None
