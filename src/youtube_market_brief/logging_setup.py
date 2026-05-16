"""Logging setup: stderr + per-day file under Harness/logs/youtube_market_brief/."""

from __future__ import annotations

import logging
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


class SecretRedactionFilter(logging.Filter):
    """Redact credentials that third-party HTTP loggers may place in URLs."""

    _telegram_bot_url = re.compile(r"bot[0-9]+:[A-Za-z0-9_-]+/sendMessage")
    _assignment = re.compile(
        r"(?i)\b("
        r"OPENAI_API_KEY|YOUTUBE_API_KEY|TELEGRAM_BOT_TOKEN|TELEGRAM_CHAT_ID|"
        r"WEBSHARE_PROXY_PASSWORD|YOUTUBE_COOKIES|YOUTUBE_COOKIE_FILE|"
        r"DRIVE_SERVICE_ACCOUNT_JSON|GDRIVE_SERVICE_ACCOUNT_JSON"
        r")=([^\s]+)"
    )
    _cookie_names = re.compile(
        r"(?i)\b(LOGIN_INFO|SAPISID|APISID|HSID|SSID|SID|__Secure-[A-Za-z0-9_-]+)=([^;\s]+)"
    )
    _bearer = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = self._redact(record.msg)
        if record.args:
            record.args = tuple(self._redact(arg) for arg in record.args)
        return True

    def _redact(self, value):
        if not isinstance(value, str):
            return value
        value = self._telegram_bot_url.sub("bot<TELEGRAM_BOT_TOKEN>/sendMessage", value)
        value = self._assignment.sub(r"\1=<redacted>", value)
        value = self._cookie_names.sub(r"\1=<redacted>", value)
        return self._bearer.sub("Bearer <redacted>", value)


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
    redactor = SecretRedactionFilter()

    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(fmt)
    sh.addFilter(redactor)
    root.addHandler(sh)

    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(fmt)
    fh.addFilter(redactor)
    root.addHandler(fh)

    logging.getLogger("httpx").setLevel(logging.WARNING)
