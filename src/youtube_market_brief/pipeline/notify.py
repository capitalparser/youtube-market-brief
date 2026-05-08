"""Telegram delivery: per-video and daily brief, with chunking + reply chaining."""

from __future__ import annotations

import logging

from youtube_market_brief._clients.telegram import TelegramClient
from youtube_market_brief.domain.telegram_format import (
    format_daily_brief,
    format_per_video,
    split_message,
)
from youtube_market_brief.domain.types import (
    DailyBrief,
    NotifyResult,
    VideoAnalysis,
)

log = logging.getLogger(__name__)


def notify_per_video(
    analysis: VideoAnalysis,
    *,
    telegram: TelegramClient,
    vault_md_path_relative: str,
) -> NotifyResult:
    text = format_per_video(analysis, vault_md_path_relative=vault_md_path_relative)
    return _send_chunks(text, telegram=telegram, target="per_video")


def notify_daily(
    brief: DailyBrief,
    *,
    telegram: TelegramClient,
) -> NotifyResult:
    text = format_daily_brief(brief)
    return _send_chunks(text, telegram=telegram, target="daily")


def _send_chunks(text: str, *, telegram: TelegramClient, target) -> NotifyResult:
    chunks = split_message(text)
    ids: list[int] = []
    reply_to: int | None = None
    try:
        for chunk in chunks:
            mid = telegram.send_message(chunk, reply_to_message_id=reply_to)
            ids.append(mid)
            reply_to = mid
    except Exception as e:
        log.error("telegram send failed at chunk %d/%d: %s", len(ids) + 1, len(chunks), e)
        return NotifyResult(target=target, ok=False, message_ids=tuple(ids), error=str(e))
    return NotifyResult(target=target, ok=True, message_ids=tuple(ids))
