"""JSON-backed idempotency store with atomic writes.

State file schema (version 1):
{
  "version": 1,
  "videos": {
     "<video_id>": {
       "processed_at": ISO8601 with offset,
       "channel_id": str,
       "outcome": "ok" | "skipped_no_caption" | "failed",
       "md_path": str | null,
     }
  },
  "daily": {
     "YYYY-MM-DD": {"brief_sent": bool, "brief_path": str | null}
  },
  "last_run": ISO8601 with offset | null
}
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from youtube_market_brief.domain.types import Outcome

_STATE_VERSION = 1


@dataclass
class VideoState:
    processed_at: datetime
    channel_id: str
    outcome: Outcome
    md_path: str | None


@dataclass
class DailyState:
    brief_sent: bool
    brief_path: str | None


class IdempotencyStore:
    def __init__(self, path: Path):
        self.path = path
        self._data: dict[str, Any] = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"version": _STATE_VERSION, "videos": {}, "daily": {}, "last_run": None}
        with self.path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if data.get("version") != _STATE_VERSION:
            raise ValueError(
                f"state.json version mismatch: expected {_STATE_VERSION}, got {data.get('version')}"
            )
        return data

    def has_video(self, video_id: str) -> bool:
        return video_id in self._data["videos"]

    def get_video(self, video_id: str) -> VideoState | None:
        raw = self._data["videos"].get(video_id)
        if raw is None:
            return None
        return VideoState(
            processed_at=datetime.fromisoformat(raw["processed_at"]),
            channel_id=raw["channel_id"],
            outcome=raw["outcome"],
            md_path=raw.get("md_path"),
        )

    def mark_video(
        self,
        video_id: str,
        *,
        channel_id: str,
        outcome: Outcome,
        md_path: str | None,
        processed_at: datetime,
    ) -> None:
        self._data["videos"][video_id] = {
            "processed_at": processed_at.isoformat(),
            "channel_id": channel_id,
            "outcome": outcome,
            "md_path": md_path,
        }

    def daily_brief_sent(self, d: date) -> bool:
        entry = self._data["daily"].get(d.isoformat())
        return bool(entry and entry.get("brief_sent"))

    def mark_daily_brief(
        self, d: date, *, brief_sent: bool, brief_path: str | None
    ) -> None:
        self._data["daily"][d.isoformat()] = {
            "brief_sent": brief_sent,
            "brief_path": brief_path,
        }

    def set_last_run(self, when: datetime) -> None:
        self._data["last_run"] = when.isoformat()

    def flush(self) -> None:
        """Atomic write: tempfile in same dir → os.replace."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(
            prefix=".state-", suffix=".json", dir=self.path.parent
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2, sort_keys=True)
            os.replace(tmp, self.path)
        except Exception:
            try:
                os.unlink(tmp)
            except FileNotFoundError:
                pass
            raise
