"""Daily brief markdown serialization and ticker rollup math."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Iterable

from youtube_market_brief.domain.types import (
    DailyBrief,
    Direction,
    NetDirection,
    TickerMention,
    TickerRollup,
    TickerRollupVideoEntry,
    VideoAnalysis,
)

_DIRECTION_EMOJI = {
    "긍정적": "🟢",
    "중립": "⚪",
    "부정적": "🔴",
    "언급만": "◽",
    "혼조": "🟡",
}


def compute_rollup(analyses: Iterable[VideoAnalysis]) -> tuple[TickerRollup, ...]:
    """Aggregate per-video TickerMention into per-ticker rollups.

    Grouping key:
    - if in_watchlist: by symbol
    - else: by display string (auto-discovered tickers without canonical symbol)
    """
    buckets: OrderedDict[tuple[bool, str], list[tuple[VideoAnalysis, TickerMention]]] = (
        OrderedDict()
    )
    for a in analyses:
        for t in a.tickers:
            key_str = t.symbol if (t.in_watchlist and t.symbol) else t.display.strip()
            if not key_str:
                continue
            key = (t.in_watchlist, key_str)
            buckets.setdefault(key, []).append((a, t))

    rollups: list[TickerRollup] = []
    for (in_wl, key_str), pairs in buckets.items():
        directions: list[Direction] = [t.direction for _, t in pairs]
        rollups.append(
            TickerRollup(
                symbol=key_str if in_wl else (pairs[0][1].symbol if pairs[0][1].symbol else None),
                display=pairs[0][1].display,
                in_watchlist=in_wl,
                net_direction=_net_direction(directions),
                mention_count=len(pairs),
                per_video=tuple(
                    TickerRollupVideoEntry(
                        video_id=a.video.video_id,
                        direction=t.direction,
                        one_line_reason=_one_line(t.reasoning),
                    )
                    for a, t in pairs
                ),
            )
        )

    rollups.sort(
        key=lambda r: (
            0 if r.in_watchlist else 1,
            -r.mention_count,
            r.symbol or r.display,
        )
    )
    return tuple(rollups)


def _net_direction(directions: list[Direction]) -> NetDirection:
    unique = set(directions)
    if len(unique) == 1:
        return next(iter(unique))
    # Multiple directions: any meaningful disagreement → 혼조
    meaningful = unique - {"언급만"}
    if len(meaningful) == 0:
        return "언급만"
    if len(meaningful) == 1:
        return next(iter(meaningful))
    return "혼조"


def _one_line(s: str, max_len: int = 80) -> str:
    s = " ".join(s.split())
    return s if len(s) <= max_len else s[: max_len - 1] + "…"


def render_daily_brief_markdown(brief: DailyBrief, *, captured_at) -> str:
    """Render the daily brief markdown document."""
    parts: list[str] = []

    # Frontmatter
    parts.append("---")
    parts.append(f"captured_at: {captured_at.isoformat()}")
    parts.append(f"date: {brief.date.isoformat()}")
    parts.append("source_type: youtube_daily_brief")
    parts.append("source_url: ''")
    parts.append("tags:")
    parts.append("  - youtube")
    parts.append("  - daily_brief")
    parts.append("tier: T3")
    parts.append("---")
    parts.append("")

    parts.append(f"# 📅 {brief.date.isoformat()} 일일 시장 브리핑\n")

    parts.append("## 🎯 오늘의 시장 read\n")
    parts.append(brief.market_read.strip() + "\n")

    parts.append("## 🔑 핵심 인사이트\n")
    for ins in brief.key_insights:
        parts.append(f"- {ins}")
    parts.append("")

    parts.append("## 🚨 레드팀 시각\n")
    for rt in brief.red_team:
        parts.append(f"- {rt}")
    parts.append("")

    wl = [r for r in brief.ticker_rollup if r.in_watchlist]
    auto = [r for r in brief.ticker_rollup if not r.in_watchlist]

    if wl:
        parts.append("## 📊 워치리스트 종목별 영향\n")
        parts.append("| 종목 | 방향 | 영상수 | 영상별 코멘트 |")
        parts.append("|------|------|--------|---------------|")
        for r in wl:
            emoji = _DIRECTION_EMOJI.get(r.net_direction, "")
            comments = "<br>".join(
                f"{e.video_id}: {e.direction} — {e.one_line_reason}" for e in r.per_video
            )
            label = f"{r.display}"
            if r.symbol:
                label += f" ({r.symbol})"
            parts.append(
                f"| {label} | {emoji} {r.net_direction} | {r.mention_count} | {comments} |"
            )
        parts.append("")

    if auto:
        parts.append("## 🔍 자동 발견 종목\n")
        for r in auto:
            emoji = _DIRECTION_EMOJI.get(r.net_direction, "")
            parts.append(
                f"- **{r.display}** {emoji} {r.net_direction} — {r.mention_count}개 영상 언급"
            )
        parts.append("")

    parts.append(f"## 📺 오늘 처리 영상 ({len(brief.videos)}건)\n")
    for v in brief.videos:
        parts.append(f"- [{v.title}]({v.url}) — {v.channel_name}")
    parts.append("")

    return "\n".join(parts).rstrip() + "\n"
