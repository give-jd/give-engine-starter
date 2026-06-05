"""Gi.Ve Engine - Lemon Squeezy license validator (client side).

Used by the orchestrator to:
  - activate a license key on this PC (returns instance_id)
  - validate periodically (15-min TTL cache)
  - deactivate (logout / move PC)
  - persist the resulting state in ~/.givengine/license.json

API surface designed to be friendly to non-technical users: any LS
error_code is translated to an italian, actionable message.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

try:
    from core import config  # type: ignore
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from core import config                        # type: ignore


LS_VALIDATE_URL = "https://api.lemonsqueezy.com/v1/licenses/validate"
LS_ACTIVATE_URL = "https://api.lemonsqueezy.com/v1/licenses/activate"
LS_DEACTIVATE_URL = "https://api.lemonsqueezy.com/v1/licenses/deactivate"

LICENSE_FILE = Path(os.path.expanduser("~/.givengine/license.json"))
CACHE_TTL_SECONDS = 15 * 60

_FRIENDLY_ERRORS: dict = {
    "license_key_invalid":      "Chiave non valida, controlla di averla copiata bene",
    "license_key_expired":      "Licenza scaduta. Rinnova su engine.givegroup.it",
    "license_key_disabled":     "Licenza disattivata. Contatta engine@givegroup.it",
    "license_key_inactive":     "Licenza non ancora attiva. Attendi qualche minuto e riprova.",
    "activation_limit_reached": "Hai raggiunto il numero massimo di attivazioni. Disattiva un altro PC dalla tua area cliente.",
    "license_key_not_found":    "Chiave non trovata. Verifica di averla copiata dall'email correttamente.",
    "instance_not_found":       "Questo PC non risulta attivato per questa licenza.",
}


@dataclass
class LicenseStatus:
    valid: bool
    tier: str = "starter"
    license_key_masked: str = ""
    instance_id: Optional[str] = None
    customer_email_masked: str = ""
    expires_at: Optional[str] = None
    validated_at: Optional[str] = None
    test_mode: bool = False
    message: str = ""
    error_code: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ActivationResult:
    success: bool
    status: LicenseStatus = field(default_factory=lambda: LicenseStatus(valid=False))
    message: str = ""
    error_code: Optional[str] = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _mask_email(email: str) -> str:
    if not email or "@" not in email:
        return "***"
    local, _, domain = email.partition("@")
    head = local[:1] if local else "?"
    if "." in domain:
        d_head, _, tld = domain.rpartition(".")
        return f"{head}***@{d_head[:1] or '?'}***.{tld}"
    return f"{head}***@{domain[:1] or '?'}***"


def _mask_key(key: str) -> str:
    if not key:
        return ""
    last4 = key[-4:]
    return f"····-····-····-{last4}"


def _default_instance_name() -> str:
    try:
        host = socket.gethostname() or "givengine-local"
    except Exception:
        host = "givengine-local"
    return f"givengine-{host}"


def _resolve_tier(variant_id) -> str:
    if not variant_id:
        return "starter"
    mapping = config.variant_to_tier_map()
    return mapping.get(str(variant_id), "starter")


def _translate_error(error_code, fallback: str) -> str:
    if not error_code:
        return fallback
    return _FRIENDLY_ERRORS.get(error_code, fallback)


def load_persisted() -> LicenseStatus:
    """Return last validated state from disk, or a default Starter status."""
    try:
        raw = LICENSE_FILE.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return LicenseStatus(valid=False, tier="starter",
                             message="Nessuna licenza attiva. Sei nel piano gratuito.")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return LicenseStatus(valid=False, tier="starter",
                             message="License file corrotto, riattiva.")
    return LicenseStatus(
        valid=bool(data.get("license_key")) and data.get("tier", "starter") != "starter",
        tier=data.get("tier", "starter"),
        license_key_masked=data.get("license_key_masked", ""),
        instance_id=data.get("instance_id"),
        customer_email_masked=data.get("customer_email_masked", ""),
        expires_at=data.get("expires_at"),
        validated_at=data.get("validated_at"),
        test_mode=bool(data.get("test_mode")),
        message="Licenza salvata su questo PC.",
    )


def _persist(status: LicenseStatus, full_key: Optional[str]) -> None:
    LICENSE_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "license_key": full_key or "",
        "license_key_masked": status.license_key_masked,
        "instance_id": status.instance_id,
        "tier": status.tier,
        "customer_email_masked": status.customer_email_masked,
        "validated_at": status.validated_at,
        "expires_at": status.expires_at,
        "test_mode": status.test_mode,
    }
    LICENSE_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    try:
        os.chmod(LICENSE_FILE, 0o600)
    except OSError:
        pass


def _persisted_full_key():
    try:
        data = json.loads(LICENSE_FILE.read_text(encoding="utf-8"))
        return data.get("license_key") or None
    except Exception:
        return None


def clear_persisted() -> None:
    try:
        LICENSE_FILE.unlink()
    except FileNotFoundError:
        pass


class LemonSqueezyLicenseValidator:
    """Wraps the three license endpoints with TTL caching + error translation."""

    def __init__(self) -> None:
        self._cache: dict = {}

    def _post(self, url: str, data: dict, timeout: float = 8.0):
        try:
            import httpx
        except ImportError:
            return 500, {"error": "httpx_missing"}
        try:
            with httpx.Client(timeout=timeout) as client:
                r = client.post(url, data=data, headers={"Accept": "application/json"})
            try:
                payload = r.json()
            except Exception:
                payload = {}
            return r.status_code, payload
        except Exception as e:
            return 502, {"error": "transport", "detail": str(e)}

    def _parse(self, body: dict, license_key: str, instance_id=None) -> LicenseStatus:
        meta = body.get("meta") or {}
        store_id_resp = str(meta.get("store_id") or "")
        store_id_env = config.get("LEMONSQUEEZY_STORE_ID")
        if store_id_env and store_id_resp and store_id_env != store_id_resp:
            return LicenseStatus(
                valid=False, tier="starter",
                license_key_masked=_mask_key(license_key),
                message="Questa chiave appartiene a un altro store, non è valida per Gi.Ve Engine.",
                error_code="store_mismatch",
            )

        variant_id = meta.get("variant_id")
        tier = _resolve_tier(variant_id)

        lic = body.get("license_key") or {}
        attrs = lic if isinstance(lic, dict) else {}
        status_label = attrs.get("status")
        expires_at = attrs.get("expires_at")
        customer_email = (meta.get("customer_email") or
                          (body.get("customer") or {}).get("email") or "")

        valid = bool(body.get("valid")) and status_label in (None, "active") and tier != "starter"

        return LicenseStatus(
            valid=valid,
            tier=tier if valid else "starter",
            license_key_masked=_mask_key(license_key),
            instance_id=instance_id or (body.get("instance") or {}).get("id"),
            customer_email_masked=_mask_email(customer_email),
            expires_at=expires_at,
            validated_at=_now_iso(),
            test_mode=bool(meta.get("test_mode")),
            message="Licenza attiva." if valid else "Licenza non attiva.",
            error_code=None if valid else body.get("error"),
        )

    def validate(self, license_key: str, instance_id=None) -> LicenseStatus:
        if not license_key:
            return LicenseStatus(valid=False, tier="starter",
                                 message="Inserisci una license key.",
                                 error_code="empty")

        cache_key = f"{license_key}|{instance_id or ''}"
        now = time.time()
        cached = self._cache.get(cache_key)
        if cached and (now - cached[0] < CACHE_TTL_SECONDS):
            return cached[1]

        payload = {"license_key": license_key}
        if instance_id:
            payload["instance_id"] = instance_id

        status_code, body = self._post(LS_VALIDATE_URL, payload)
        if status_code == 500 and body.get("error") == "httpx_missing":
            return LicenseStatus(valid=False, tier="starter",
                                 message="Dipendenza httpx mancante: pip install -r requirements.txt",
                                 error_code="httpx_missing")
        if status_code >= 500:
            return LicenseStatus(valid=False, tier="starter",
                                 message="Servizio licenze temporaneamente non disponibile, riprova tra un attimo.",
                                 error_code="upstream_unavailable")

        if not body:
            return LicenseStatus(valid=False, tier="starter",
                                 message="Risposta vuota dal servizio licenze.",
                                 error_code="empty_response")

        status = self._parse(body, license_key, instance_id)
        if not status.valid:
            status.message = _translate_error(status.error_code, status.message)
        self._cache[cache_key] = (now, status)
        return status

    def activate(self, license_key: str, instance_name=None) -> ActivationResult:
        if not license_key:
            return ActivationResult(success=False, message="Inserisci una license key.", error_code="empty")

        instance_name = instance_name or _default_instance_name()
        status_code, body = self._post(LS_ACTIVATE_URL, {
            "license_key": license_key,
            "instance_name": instance_name,
        })
        if status_code == 500 and body.get("error") == "httpx_missing":
            return ActivationResult(success=False,
                                    message="Dipendenza httpx mancante.",
                                    error_code="httpx_missing")
        if status_code >= 500:
            return ActivationResult(success=False,
                                    message="Servizio licenze temporaneamente non disponibile.",
                                    error_code="upstream_unavailable")

        status = self._parse(body, license_key, (body.get("instance") or {}).get("id"))
        if not status.valid:
            status.message = _translate_error(status.error_code, "Attivazione fallita.")
            return ActivationResult(success=False, status=status,
                                    message=status.message,
                                    error_code=status.error_code)

        status.message = f"Licenza attivata. Benvenuto nel piano {status.tier.capitalize()}!"
        _persist(status, full_key=license_key)
        return ActivationResult(success=True, status=status, message=status.message)

    def deactivate(self, license_key=None, instance_id=None) -> bool:
        if not license_key or not instance_id:
            persisted = load_persisted()
            license_key = license_key or _persisted_full_key()
            instance_id = instance_id or persisted.instance_id
        if not license_key or not instance_id:
            clear_persisted()
            return True

        status_code, _ = self._post(LS_DEACTIVATE_URL, {
            "license_key": license_key,
            "instance_id": instance_id,
        })
        clear_persisted()
        return status_code < 400


_validator = None


def validator() -> LemonSqueezyLicenseValidator:
    global _validator
    if _validator is None:
        _validator = LemonSqueezyLicenseValidator()
    return _validator


def current_status(refresh: bool = False) -> LicenseStatus:
    """Snapshot used by the orchestrator at startup + by /license/status."""
    persisted = load_persisted()
    if not persisted.valid:
        return persisted

    if refresh:
        full = _persisted_full_key()
        if full:
            fresh = validator().validate(full, persisted.instance_id)
            if fresh.valid:
                _persist(fresh, full_key=full)
                return fresh
            clear_persisted()
            fresh.message = _translate_error(fresh.error_code, fresh.message)
            return fresh

    return persisted


def current_tier() -> str:
    return current_status().tier or "starter"
