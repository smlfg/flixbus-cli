"""Pytest-Konfiguration: ``src/`` vor jeder anderen Import-Quelle einbinden,
damit die Tests gegen den Quellcode laufen, nicht gegen eine installierte Version."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT / "src"))
