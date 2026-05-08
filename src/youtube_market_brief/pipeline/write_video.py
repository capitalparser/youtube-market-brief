"""Write per-video markdown to vault."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from youtube_market_brief.domain.markdown import render_video_markdown
from youtube_market_brief.domain.slugify import video_slug
from youtube_market_brief.domain.types import VideoAnalysis

log = logging.getLogger(__name__)


def write_video_md(
    analysis: VideoAnalysis,
    *,
    vault_youtube_root: Path,
    captured_at: datetime,
    date_kst_iso: str,
) -> Path:
    """Write the per-video MD. Returns the absolute path written.

    Path layout: {vault_youtube_root}/{channel_slug}/{date_iso}__{video_slug}.md
    """
    channel_dir = vault_youtube_root / analysis.video.channel_slug
    channel_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{date_kst_iso}__{video_slug(analysis.video.title, analysis.video.video_id)}.md"
    out = channel_dir / fname
    body = render_video_markdown(analysis, captured_at=captured_at)
    out.write_text(body, encoding="utf-8")
    log.info("wrote video MD: %s (%d bytes)", out, len(body.encode("utf-8")))
    return out
