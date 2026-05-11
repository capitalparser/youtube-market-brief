"""Telegram Bot API client (HTTPS, sendMessage). Supports dry-run mode."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

import httpx


class TelegramClient(Protocol):
    def send_message(
        self,
        text: str,
        *,
        reply_to_message_id: int | None = None,
    ) -> int:
        """Send a message. Return Telegram message_id. Raises on failure."""
        ...


class HttpxTelegramClient:
    def __init__(self, *, bot_token: str, chat_id: str, timeout_sec: float = 30.0):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.timeout_sec = timeout_sec
        self._url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    def send_message(
        self,
        text: str,
        *,
        reply_to_message_id: int | None = None,
    ) -> int:
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if reply_to_message_id is not None:
            payload["reply_to_message_id"] = reply_to_message_id
        resp = httpx.post(self._url, json=payload, timeout=self.timeout_sec)
        resp.raise_for_status()
        body = resp.json()
        if not body.get("ok"):
            raise TelegramSendError(f"Telegram API not ok: {body}")
        return int(body["result"]["message_id"])


class DryRunTelegramClient:
    """Writes messages to a sink directory instead of sending. Used in tests / DRY_RUN=true."""

    def __init__(self, sink_dir: Path):
        self.sink_dir = sink_dir
        self.sink_dir.mkdir(parents=True, exist_ok=True)
        self._counter = 0

    def send_message(
        self,
        text: str,
        *,
        reply_to_message_id: int | None = None,
    ) -> int:
        self._counter += 1
        ts = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
        out = self.sink_dir / f"{ts}_{self._counter:04d}.txt"
        header = []
        if reply_to_message_id is not None:
            header.append(f"reply_to: {reply_to_message_id}")
        header.append(f"len: {len(text)}")
        header.append("---")
        out.write_text("\n".join(header) + "\n" + text + "\n", encoding="utf-8")
        return self._counter


class TelegramSendError(RuntimeError):
    pass
