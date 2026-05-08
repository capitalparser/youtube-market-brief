"""Transcript fetch with optional truncation for LLM context safety."""

from __future__ import annotations

import logging

from youtube_market_brief._clients.transcript import TranscriptClient
from youtube_market_brief.domain.types import (
    Transcript,
    TranscriptSkip,
    VideoMeta,
)

log = logging.getLogger(__name__)


def fetch_transcript(
    video: VideoMeta,
    *,
    client: TranscriptClient,
    max_chars: int = 80_000,
) -> Transcript | TranscriptSkip:
    """Fetch and (if needed) truncate a transcript.

    Truncation strategy when over `max_chars`:
        head 60% + middle 10% + tail 30%   (markers inserted)
    Sets `was_truncated=True`.
    """
    result = client.fetch(video.video_id)
    if isinstance(result, TranscriptSkip):
        return result

    if result.char_count <= max_chars:
        return result

    full = result.full_text
    head = int(max_chars * 0.6)
    tail = int(max_chars * 0.3)
    mid_room = max_chars - head - tail
    middle_start = (len(full) - mid_room) // 2
    truncated = (
        full[:head]
        + "\n\n[…HEAD/TAIL TRUNCATION ELISION…]\n\n"
        + full[middle_start : middle_start + mid_room]
        + "\n\n[…HEAD/TAIL TRUNCATION ELISION…]\n\n"
        + full[-tail:]
    )
    log.warning("truncated transcript for %s (%d → %d chars)", video.video_id, result.char_count, len(truncated))
    return Transcript(
        video_id=result.video_id,
        language=result.language,
        is_auto_generated=result.is_auto_generated,
        segments=(),  # segments dropped after truncation
        full_text=truncated,
        char_count=len(truncated),
        fetched_at=result.fetched_at,
        was_truncated=True,
    )
