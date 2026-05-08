"""Pytest path setup so `tests.fakes...` imports work without install."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"

for p in (ROOT, SRC):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)
