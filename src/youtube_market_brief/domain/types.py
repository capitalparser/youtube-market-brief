"""Frozen dataclasses for the pipeline. client-free, deterministic."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal

Market = Literal["KOSPI", "KOSDAQ", "NYSE", "NASDAQ", "ETC"]
Direction = Literal["긍정적", "중립", "부정적", "언급만"]
NetDirection = Literal["긍정적", "중립", "부정적", "혼조", "언급만"]
Confidence = Literal["high", "medium", "low"]
Tier = Literal["light", "deep"]
SkipReason = Literal["no_captions", "disabled", "geo_blocked", "api_changed", "timeout"]
Outcome = Literal["ok", "skipped_no_caption", "failed"]
NotifyTarget = Literal["per_video", "daily"]


@dataclass(frozen=True)
class VideoMeta:
    video_id: str
    channel_id: str
    channel_name: str
    channel_slug: str
    title: str
    published_at_utc: datetime
    url: str
    duration_sec: int | None = None


@dataclass(frozen=True)
class Segment:
    start: float
    duration: float
    text: str


@dataclass(frozen=True)
class Transcript:
    video_id: str
    language: str
    is_auto_generated: bool
    segments: tuple[Segment, ...]
    full_text: str
    char_count: int
    fetched_at: datetime
    was_truncated: bool = False


@dataclass(frozen=True)
class TranscriptSkip:
    video_id: str
    reason: SkipReason
    detail: str


@dataclass(frozen=True)
class WatchlistEntry:
    symbol: str
    market: Market
    name_ko: str
    sector: str = ""             # NEW, defaulted
    name_en: str | None = None
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class Watchlist:
    entries: tuple[WatchlistEntry, ...] = ()

    def is_empty(self) -> bool:
        return len(self.entries) == 0

    def by_symbol(self) -> dict[str, WatchlistEntry]:
        return {e.symbol: e for e in self.entries}


@dataclass(frozen=True)
class KeyInsight:
    text: str
    sector_tags: tuple[str, ...] = ()
    theme_tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class RedTeamItem:
    text: str
    sector_tags: tuple[str, ...] = ()
    theme_tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class TickerMention:
    symbol: str | None
    display: str
    in_watchlist: bool
    sector_tag: str | None      # NEW
    direction: Direction
    reasoning: str
    quotes: tuple[str, ...]
    confidence: Confidence


@dataclass(frozen=True)
class TranscriptSummary:
    headline_3line: tuple[str, str, str]
    key_insights: tuple[KeyInsight, ...]
    red_team: tuple[RedTeamItem, ...]
    chars_used: int
    was_truncated: bool


@dataclass(frozen=True)
class LLMMeta:
    model: str
    duration_ms: int
    was_retry: bool = False
    claude_session_id: str | None = None


@dataclass(frozen=True)
class VideoAnalysis:
    video: VideoMeta
    transcript_summary: TranscriptSummary
    tickers: tuple[TickerMention, ...]
    watchlist_hits: tuple[str, ...]
    tier: Tier
    tags: tuple[str, ...]
    llm_meta: LLMMeta
    generated_at: datetime


@dataclass(frozen=True)
class TickerRollupVideoEntry:
    video_id: str
    direction: Direction
    one_line_reason: str


@dataclass(frozen=True)
class TickerRollup:
    symbol: str | None
    display: str
    in_watchlist: bool
    net_direction: NetDirection
    mention_count: int
    per_video: tuple[TickerRollupVideoEntry, ...]


@dataclass(frozen=True)
class DailyBrief:
    date: date
    market_read: str
    # NOTE: still tuple[str, ...] during P1 migration; promoted to KeyInsight/RedTeamItem tuples in Task 7.
    key_insights: tuple[str, ...]
    red_team: tuple[str, ...]
    ticker_rollup: tuple[TickerRollup, ...]
    videos: tuple[VideoMeta, ...]
    llm_meta: LLMMeta


@dataclass(frozen=True)
class NotifyResult:
    target: NotifyTarget
    ok: bool
    message_ids: tuple[int, ...] = ()
    error: str | None = None


@dataclass(frozen=True)
class RunFailure:
    video_id: str
    error_class: str
    message: str


@dataclass
class RunReport:
    date: date
    discovered: int = 0
    processed: int = 0
    skipped_no_caption: int = 0
    skipped_idempotent: int = 0
    failed: list[RunFailure] = field(default_factory=list)
    duration_sec: float = 0.0
    daily_brief_generated: bool = False
    daily_brief_sent: bool = False


@dataclass(frozen=True)
class ChannelConfig:
    name_ko: str
    slug: str
    enabled: bool
    channel_id: str | None = None
    handle: str | None = None
    notes: str | None = None
