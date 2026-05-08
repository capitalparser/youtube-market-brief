"""Logging setup: stderr + per-day file under Harness/logs/youtube_market_brief/."""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


def setup_logging(*, level: str, logs_dir: Path, tz: ZoneInfo) -> None:
    logs_dir.mkdir(parents=True, exist_ok=True)
    today_kst = datetime.now(tz).strftime("%Y-%m-%d")
    log_path = logs_dir / f"{today_kst}.log"

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    # Clear any pre-existing handlers (re-runs in tests / repl)
    for h in list(root.handlers):
        root.removeHandler(h)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )

    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(fmt)
    root.addHandler(sh)

    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)
