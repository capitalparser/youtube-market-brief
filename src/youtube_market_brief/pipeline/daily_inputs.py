"""Load canonical per-video analysis sidecars for daily aggregation."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

from youtube_market_brief.domain.types import (
    KeyInsight,
    LLMMeta,
    RedTeamItem,
    TickerMention,
    TranscriptSummary,
    VideoAnalysis,
    VideoMeta,
)


def load_video_analyses_for_date(
    *,
    vault_youtube_root: Path,
    target_date: date,
) -> list[VideoAnalysis]:
    """Load per-video `.analysis.json` sidecars for `target_date`.

    Daily aggregation should prefer these sidecars over parsing rendered
    Markdown, because sidecars preserve typed ticker, sector, and tag fields.
    """
    pattern = f"{target_date.isoformat()}__*.analysis.json"
    paths = sorted(vault_youtube_root.glob(f"*/{pattern}"))
    paths = [p for p in paths if not p.parent.name.startswith("_")]
    return [_load_video_analysis_sidecar(p) for p in paths]


def _load_video_analysis_sidecar(path: Path) -> VideoAnalysis:
    data = json.loads(path.read_text(encoding="utf-8"))
    video_raw = data.get("video") or {}
    transcript_meta = data.get("transcript_meta") or {}
    llm_meta = data.get("llm_meta") or {}

    video = VideoMeta(
        video_id=str(video_raw.get("video_id", "")),
        channel_id=str(video_raw.get("channel_id", "")),
        channel_name=str(video_raw.get("channel_name", "")),
        channel_slug=str(video_raw.get("channel_slug", "")),
        title=str(video_raw.get("title", "")),
        published_at_utc=_parse_dt(video_raw.get("published_at_utc")),
        url=str(video_raw.get("url", "")),
        duration_sec=video_raw.get("duration_sec"),
    )
    return VideoAnalysis(
        video=video,
        transcript_summary=TranscriptSummary(
            headline_3line=_headline(data.get("headline_3line") or []),
            key_insights=tuple(_reasoning_item(i, KeyInsight) for i in data.get("key_insights") or []),
            red_team=tuple(_reasoning_item(i, RedTeamItem) for i in data.get("red_team") or []),
            chars_used=int(transcript_meta.get("chars_used", 0)),
            was_truncated=bool(transcript_meta.get("was_truncated", False)),
        ),
        tickers=tuple(_ticker(t) for t in data.get("tickers") or [] if isinstance(t, dict)),
        watchlist_hits=tuple(data.get("watchlist_hits") or []),
        tier=data.get("tier", "light"),
        tags=tuple(data.get("tags") or []),
        llm_meta=LLMMeta(
            model=str(llm_meta.get("model", "")),
            duration_ms=int(llm_meta.get("duration_ms", 0)),
            was_retry=bool(llm_meta.get("was_retry", False)),
            claude_session_id=llm_meta.get("claude_session_id"),
        ),
        generated_at=_parse_dt(data.get("generated_at")),
    )


def _parse_dt(value) -> datetime:
    if value:
        return datetime.fromisoformat(str(value))
    return datetime.fromisoformat("1970-01-01T00:00:00+00:00")


def _headline(raw: list) -> tuple[str, str, str]:
    items = [str(x) for x in raw[:3]]
    return tuple(items + [""] * (3 - len(items)))  # type: ignore[return-value]


def _reasoning_item(raw, cls):
    if not isinstance(raw, dict):
        return cls(text=str(raw), sector_tags=(), theme_tags=())
    return cls(
        text=str(raw.get("text", "")),
        sector_tags=tuple(raw.get("sector_tags") or []),
        theme_tags=tuple(raw.get("theme_tags") or []),
        why_important=str(raw.get("why_important", "")).strip(),
        structural_shift=str(raw.get("structural_shift", "")).strip(),
        pattern_connection=str(raw.get("pattern_connection", "")).strip(),
        counter_signal=str(raw.get("counter_signal", "")).strip(),
        workflow_implication=str(raw.get("workflow_implication", "")).strip(),
        signal_density=str(raw.get("signal_density", "")).strip(),
    )


def _ticker(raw: dict) -> TickerMention:
    return TickerMention(
        symbol=raw.get("symbol"),
        display=str(raw.get("display", "")),
        in_watchlist=bool(raw.get("in_watchlist", False)),
        sector_tag=raw.get("sector_tag"),
        direction=raw.get("direction", "언급만"),
        reasoning=str(raw.get("reasoning", "")),
        quotes=tuple(raw.get("quotes") or []),
        confidence=raw.get("confidence", "low"),
    )
