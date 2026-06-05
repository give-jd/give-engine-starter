"""Smoke test per spese-casalinghe inject.py.

Verifica che il template inject produca un bundle minimo valido in una out dir
temporanea, senza side effects fuori dalla tmp. Zero network — solo Jinja2 + fs.
"""

from __future__ import annotations

import sys
from pathlib import Path

RECIPE_DIR = Path(__file__).resolve().parents[1]
if str(RECIPE_DIR) not in sys.path:
    sys.path.insert(0, str(RECIPE_DIR))

import inject  # noqa: E402


def test_load_recipe_yaml_ok():
    recipe = inject.load_recipe()
    assert recipe["id"] == "spese-casalinghe"
    assert "porta_locale" in recipe
    assert "streamlit_entrypoint" in recipe


def test_build_writes_bundle(tmp_path):
    report = inject.build(output_dir=str(tmp_path))
    assert report["output_dir"] == str(tmp_path)
    assert len(report["files_written"]) > 0
    # AGENTS.md + config streamlit sempre prodotti
    assert (tmp_path / "AGENTS.md").exists()
    assert (tmp_path / ".streamlit" / "config.toml").exists()


def test_build_no_side_effects_outside_tmp(tmp_path):
    before = {p.name for p in RECIPE_DIR.iterdir()}
    inject.build(output_dir=str(tmp_path))
    after = {p.name for p in RECIPE_DIR.iterdir()}
    assert before == after  # nessun file creato nella dir ricetta


def test_rendered_files_are_under_out_dir(tmp_path):
    report = inject.build(output_dir=str(tmp_path))
    for rel in report["files_written"]:
        assert (tmp_path / rel).exists()
