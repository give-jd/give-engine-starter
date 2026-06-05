"""Rende importabili i moduli top-level `core/*.py` come `from core import X`.

Aggiunge la root del monorepo a sys.path (i moduli core non sono un package
installato; i test girano da ROOT).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
