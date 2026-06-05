"""Inject the spese-casalinghe recipe into a user-chosen output folder.

Renders every *.jinja template under ./templates/, copies non-Jinja files
verbatim, drops a kanji-compressed AGENTS.md so background agents read the
same brief in their machine dialect, and writes a Streamlit dark-theme
config.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.caveman_optimizer import CavemanOptimizer  # noqa: E402


RECIPE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = RECIPE_DIR / "templates"


STREAMLIT_DARK_CONFIG = """\
[theme]
base = "dark"
primaryColor = "#7c3aed"
backgroundColor = "#0b1020"
secondaryBackgroundColor = "#131a33"
textColor = "#e2e8f0"
font = "sans serif"

[server]
headless = true
"""


def load_recipe() -> dict:
    return yaml.safe_load((RECIPE_DIR / "recipe.yaml").read_text(encoding="utf-8"))


def _render_templates(out_dir: Path, context: dict) -> list[str]:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        autoescape=select_autoescape(
            enabled_extensions=("html", "xml", "svg"),
            default_for_string=False,
        ),
    )
    written: list[str] = []
    for src in TEMPLATES_DIR.iterdir():
        if src.is_dir():
            continue
        if src.suffix == ".jinja":
            target_name = src.stem
            tpl = env.get_template(src.name)
            content = tpl.render(**context)
        else:
            target_name = src.name
            content = src.read_text(encoding="utf-8")

        dest = out_dir / target_name
        dest.write_text(content, encoding="utf-8")
        written.append(target_name)
    return written


def _write_agents_md(out_dir: Path, recipe_id: str) -> None:
    opt = CavemanOptimizer(out_dir)
    text = opt.generate_agents_md(recipe_id, recipes_root=RECIPE_DIR.parent)
    (out_dir / "AGENTS.md").write_text(text, encoding="utf-8")


def _write_streamlit_config(out_dir: Path) -> None:
    (out_dir / ".streamlit").mkdir(exist_ok=True)
    (out_dir / ".streamlit" / "config.toml").write_text(
        STREAMLIT_DARK_CONFIG, encoding="utf-8"
    )


def _resolve_out_dir(recipe: dict, override: Optional[str]) -> Path:
    candidate = override or recipe.get("output_dir_default", "~/GiveEngine_apps/spese-casalinghe")
    return Path(os.path.expanduser(candidate)).resolve()


def build(
    output_dir: Optional[str] = None,
    answers: Optional[dict] = None,
) -> dict:
    """Materialize the recipe into a user folder. Returns a small report."""
    answers = answers or {}
    recipe = load_recipe()
    out_dir = _resolve_out_dir(recipe, output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    context = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "recipe": recipe,
        "answers": answers,
    }
    files_written = _render_templates(out_dir, context)
    _write_streamlit_config(out_dir)
    _write_agents_md(out_dir, recipe["id"])

    return {
        "output_dir": str(out_dir),
        "files_written": files_written + [".streamlit/config.toml", "AGENTS.md"],
        "porta_locale": recipe["porta_locale"],
        "streamlit_entrypoint": recipe["streamlit_entrypoint"],
        "expose_lan": "Sì" in str(answers.get("q1", "")),
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Inject the spese-casalinghe recipe")
    parser.add_argument("--out", help="Output folder (default: ~/GiveEngine_apps/spese-casalinghe)")
    parser.add_argument("--answer-q1", choices=["sì", "no"], default="no",
                        help="Risposta alla domanda human-in-loop sull'accesso da telefono")
    args = parser.parse_args()

    answers = {"q1": "Sì, accesso da telefono" if args.answer_q1 == "sì" else "No, solo dal mio PC"}
    report = build(output_dir=args.out, answers=answers)
    print(json.dumps(report, indent=2, ensure_ascii=False))
