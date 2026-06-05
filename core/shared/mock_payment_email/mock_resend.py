"""Mock Resend email sender — preview locale, ZERO chiamate di rete.

Used by `landing-saas-premium` v0.2 (Punto 22 KEY-DECISIONS) to preview
transactional email templates in the Cabina di Regia editor without
contacting any external email provider.

Invariants:
- No HTTP calls. Verified by tests/test_mock_email.py via mocker patching.
- Renders Jinja2 templates with user-supplied variables.
- Saves HTML output to ~/.givengine/data/landing-saas-premium/mock-mails/<ts>-<template>.html
- Returns file path + file:// URL for browser opening.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    from jinja2 import Environment, FileSystemLoader, select_autoescape
except ImportError:  # pragma: no cover
    Environment = None  # type: ignore

MOCK_MAILS_DIR = Path.home() / ".givengine" / "data" / "landing-saas-premium" / "mock-mails"
VALID_TEMPLATES = {"thanks", "welcome", "confirm", "reset"}


def render_and_save(
    project_slug: str,
    template: str,
    variables: Optional[dict] = None,
    destinatario_simulato: str = "mario.rossi@example.test",
    emails_dir: Optional[Path] = None,
) -> dict:
    """Render template email and save it locally. No network."""
    if Environment is None:
        raise ImportError("jinja2 required for mock_resend.render_and_save")
    if template not in VALID_TEMPLATES:
        raise ValueError(f"Template sconosciuto: {template} (validi: {sorted(VALID_TEMPLATES)})")

    MOCK_MAILS_DIR.mkdir(parents=True, exist_ok=True)

    if emails_dir is None:
        emails_dir = _default_emails_dir()

    env = Environment(
        loader=FileSystemLoader(str(emails_dir)),
        autoescape=select_autoescape(["html", "htm"]),
    )
    tpl = env.get_template(f"{template}.html")

    default_vars = {
        "destinatario": destinatario_simulato,
        "anno": datetime.now().year,
        "nome_prodotto": "[Nome prodotto]",
        "importo": "0",
        "billing": "mese",
        "magic_link": "https://example.test/confirm?token=mock",
        "reset_link": "https://example.test/reset?token=mock",
    }
    if variables:
        default_vars.update(variables)

    html = tpl.render(**default_vars)

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"{ts}-{template}.html"
    file_path = MOCK_MAILS_DIR / filename
    file_path.write_text(html, encoding="utf-8")

    return {
        "template": template,
        "project_slug": project_slug,
        "destinatario": destinatario_simulato,
        "file_path": str(file_path),
        "open_url": file_path.as_uri(),
    }


def _default_emails_dir() -> Path:
    here = Path(__file__).resolve()
    repo_root = here.parents[3]
    return repo_root / "core" / "recipes" / "landing-saas-premium" / "templates" / "emails"
