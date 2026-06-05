"""Smoke tests for osservaprezzi-carburanti.

Verifica minima v1.0.0:
- recipe.yaml è parsabile + versione 1.x
- app.py syntax-clean
- (se schema.sql presente) schema applicabile a SQLite vuoto
"""

from __future__ import annotations

import ast
import sys
import sqlite3
from pathlib import Path

import pytest
import yaml

RECIPE_DIR = Path(__file__).resolve().parents[1]
if str(RECIPE_DIR) not in sys.path:
    sys.path.insert(0, str(RECIPE_DIR))


def test_recipe_yaml_loadable():
    data = yaml.safe_load((RECIPE_DIR / "recipe.yaml").read_text(encoding="utf-8"))
    assert data["id"] == "osservaprezzi-carburanti"
    assert data["tier"] in ("starter", "catalog", "all-access")
    version = str(data.get("versione") or data.get("version", ""))
    assert version.startswith("1."), f"expected versione 1.x, got {version!r}"


def test_app_py_syntax_ok():
    src = (RECIPE_DIR / "app.py").read_text(encoding="utf-8")
    ast.parse(src)


def test_schema_sql_applicable_if_present():
    schema = RECIPE_DIR / "schema.sql"
    if not schema.exists():
        pytest.skip("no schema.sql")
    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript(schema.read_text(encoding="utf-8"))
    finally:
        conn.close()
