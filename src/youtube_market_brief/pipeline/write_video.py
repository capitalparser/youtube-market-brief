"""Write per-video markdown to vault."""

from __future__ import annotations

import json
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
    """Write the per-video MD + JSON sidecar. Returns the absolute path of the MD."""
    channel_dir = vault_youtube_root / analysis.video.channel_slug
    channel_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{date_kst_iso}__{video_slug(analysis.video.title, analysis.video.video_id)}.md"
    out = channel_dir / fname
    existing = sorted(channel_dir.glob(f"*-{analysis.video.video_id}.md"))
    if existing and out not in existing:
        out = existing[0]
        log.warning("reusing existing MD for video_id=%s: %s", analysis.video.video_id, out)
    body = render_video_markdown(analysis, captured_at=captured_at)
    out.write_text(body, encoding="utf-8")
    log.info("wrote video MD: %s (%d bytes)", out, len(body.encode("utf-8")))

    sidecar = out.with_suffix(".analysis.json")
    sidecar_data = _serialize_analysis_for_sidecar(analysis, captured_at=captured_at)
    sidecar.write_text(
        json.dumps(sidecar_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log.info("wrote analysis sidecar: %s", sidecar)

    return out


def _serialize_analysis_for_sidecar(a: VideoAnalysis, *, captured_at: datetime) -> dict:
    return {
        "video": {
            "video_id": a.video.video_id,
            "channel_id": a.video.channel_id,
            "channel_name": a.video.channel_name,
            "channel_slug": a.video.channel_slug,
            "title": a.video.title,
            "url": a.video.url,
            "published_at_utc": a.video.published_at_utc.isoformat(),
        },
        "captured_at": captured_at.isoformat(),
        "generated_at": a.generated_at.isoformat(),
        "headline_3line": list(a.transcript_summary.headline_3line),
        "key_insights": [
            {"text": ki.text, "sector_tags": list(ki.sector_tags), "theme_tags": list(ki.theme_tags)}
            for ki in a.transcript_summary.key_insights
        ],
        "red_team": [
            {"text": rt.text, "sector_tags": list(rt.sector_tags), "theme_tags": list(rt.theme_tags)}
            for rt in a.transcript_summary.red_team
        ],
        "tickers": [
            {
                "symbol": t.symbol,
                "display": t.display,
                "in_watchlist": t.in_watchlist,
                "sector_tag": t.sector_tag,
                "direction": t.direction,
                "reasoning": t.reasoning,
                "quotes": list(t.quotes),
                "confidence": t.confidence,
            }
            for t in a.tickers
        ],
        "watchlist_hits": list(a.watchlist_hits),
        "tier": a.tier,
        "tags": list(a.tags),
        "transcript_meta": {
            "chars_used": a.transcript_summary.chars_used,
            "was_truncated": a.transcript_summary.was_truncated,
        },
        "llm_meta": {
            "model": a.llm_meta.model,
            "duration_ms": a.llm_meta.duration_ms,
            "was_retry": a.llm_meta.was_retry,
            "claude_session_id": a.llm_meta.claude_session_id,
        },
    }
