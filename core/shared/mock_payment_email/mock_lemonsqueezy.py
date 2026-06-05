"""Mock Lemon Squeezy checkout — preview locale, ZERO chiamate di rete.

Used by `landing-saas-premium` v0.2 (Punto 22 KEY-DECISIONS) to preview
checkout flow in the Cabina di Regia editor without touching the real
Lemon Squeezy API.

Invariants:
- No HTTP calls. Tests verify via mocker patching of requests/httpx.
- Only test card "4242 4242 4242 4242" accepted (Stripe convention).
- Returns fake transaction ID for UI feedback.
- Anti-confusion: response always includes 'preview_warning' field.
"""
from __future__ import annotations

import secrets
import time

VALID_TEST_CARDS = {"4242 4242 4242 4242", "4242424242424242"}
VALID_BILLINGS = {"monthly", "yearly"}


def mock_checkout(
    tier_id: int,
    billing: str,
    email_simulata: str = "test@example.test",
    card_simulata: str = "4242 4242 4242 4242",
    simulate_latency_ms: int = 0,
) -> dict:
    """Simulate Lemon.js checkout. No network, no persistence."""
    if simulate_latency_ms > 0:
        time.sleep(simulate_latency_ms / 1000.0)

    if billing not in VALID_BILLINGS:
        return {
            "success": False,
            "transaction_id_simulato": "",
            "message": f"Billing non valido. Usa: {sorted(VALID_BILLINGS)}",
            "preview_warning": "ANTEPRIMA LOCALE — NESSUN PAGAMENTO REALE",
        }

    card_norm = (card_simulata or "").replace(" ", "")
    if card_norm not in {c.replace(" ", "") for c in VALID_TEST_CARDS}:
        return {
            "success": False,
            "transaction_id_simulato": "",
            "message": "Usa la carta di test 4242 4242 4242 4242 (no pagamento reale).",
            "preview_warning": "ANTEPRIMA LOCALE — NESSUN PAGAMENTO REALE",
        }

    fake_tx = "mock_tx_" + secrets.token_hex(8)
    return {
        "success": True,
        "transaction_id_simulato": fake_tx,
        "message": (
            f"Checkout simulato OK per tier_id={tier_id}, billing={billing}. "
            "Nessun pagamento è stato effettuato."
        ),
        "preview_warning": "ANTEPRIMA LOCALE — NESSUN PAGAMENTO REALE",
        "tier_id": tier_id,
        "billing": billing,
        "email_simulata": email_simulata,
    }
