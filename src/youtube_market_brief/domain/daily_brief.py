"""Daily brief markdown serialization and ticker rollup math."""

from __future__ import annotations

import yaml
from collections import Counter, OrderedDict
from collections.abc import Iterable
from datetime import date as Date, timedelta

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


def _yaml_inline_list(items: list[str]) -> str:
    """Emit a YAML flow-style sequence: [a, b] or []."""
    return yaml.safe_dump(items, default_flow_style=True, allow_unicode=True).strip()


def render_daily_brief_markdown(brief: DailyBrief, *, captured_at) -> str:
    """Render the daily brief markdown document."""
    parts: list[str] = []

    # Aggregate sector/theme tag union (mirrors video MD frontmatter footprint)
    ki_sectors = sorted({tag for ki in brief.key_insights for tag in ki.sector_tags})
    ki_themes = sorted({tag for ki in brief.key_insights for tag in ki.theme_tags})
    rt_sectors = sorted({tag for rt in brief.red_team for tag in rt.sector_tags})
    rt_themes = sorted({tag for rt in brief.red_team for tag in rt.theme_tags})

    parts.append("---")
    parts.append(f"captured_at: {captured_at.isoformat()}")
    parts.append(f"date: {brief.date.isoformat()}")
    parts.append(f"insight_sector_tags: {_yaml_inline_list(ki_sectors)}")
    parts.append(f"insight_theme_tags: {_yaml_inline_list(ki_themes)}")
    parts.append(f"red_team_sector_tags: {_yaml_inline_list(rt_sectors)}")
    parts.append(f"red_team_theme_tags: {_yaml_inline_list(rt_themes)}")
    parts.append("source_type: youtube_daily_brief")
    parts.append("source_url: ''")
    parts.append("tags:")
    parts.append("  - youtube")
    parts.append("  - daily_brief")
    parts.append("tier: deep")
    parts.append("---")
    parts.append("")

    parts.append(f"# 📅 {brief.date.isoformat()} 일일 시장 브리핑\n")

    parts.append("## 🎯 오늘의 시장 read\n")
    parts.append(brief.market_read.strip() + "\n")

    parts.append("## 🔑 핵심 인사이트\n")
    for ins in brief.key_insights:
        parts.append(f"- {ins.text}")
    parts.append("")

    parts.append("## 🚨 레드팀 시각\n")
    for rt in brief.red_team:
        parts.append(f"- {rt.text}")
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


def compute_weekly_rollup(
    briefs: Iterable[DailyBrief],
    *,
    week_start: Date,
) -> "WeeklyRollup | None":
    """Aggregate up to 7 daily briefs into a WeeklyRollup. Deterministic, no LLM.

    week_start should be the Monday of the target week. week_end = week_start + 6 days.
    Briefs outside this range are silently filtered.
    """
    from youtube_market_brief.domain.types import (
        WeeklyRollup,
        WeeklyTickerEntry,
        WeeklyTickerDayEntry,
        WeeklySectorEntry,
        WeeklyThemeEntry,
    )

    week_end = week_start + timedelta(days=6)
    bl = sorted(
        [b for b in briefs if week_start <= b.date <= week_end],
        key=lambda b: b.date,
    )
    if not bl:
        return None

    present_dates = tuple(b.date for b in bl)
    missing_dates = tuple(
        week_start + timedelta(days=i)
        for i in range(7)
        if (week_start + timedelta(days=i)) not in present_dates
    )

    # === Ticker aggregation: bucket by (in_watchlist, key_str) ===
    ticker_buckets: dict[tuple[bool, str], list[tuple[Date, TickerRollup]]] = {}
    for b in bl:
        for tr in b.ticker_rollup:
            key_str = tr.symbol if (tr.in_watchlist and tr.symbol) else tr.display.strip()
            if not key_str:
                continue
            key = (tr.in_watchlist, key_str)
            ticker_buckets.setdefault(key, []).append((b.date, tr))

    ticker_entries: list[WeeklyTickerEntry] = []
    for (in_wl, _key_str), day_pairs in ticker_buckets.items():
        directions = tuple(tr.net_direction for _, tr in day_pairs)
        total_mentions = sum(tr.mention_count for _, tr in day_pairs)
        per_day = tuple(
            WeeklyTickerDayEntry(
                date=d, direction=tr.net_direction, mention_count=tr.mention_count,
            )
            for d, tr in day_pairs
        )
        first_tr = day_pairs[0][1]
        ticker_entries.append(
            WeeklyTickerEntry(
                symbol=first_tr.symbol or None,
                display=first_tr.display,
                in_watchlist=in_wl,
                sector_tag=None,  # ticker_rollup doesn't carry sector — P3 MVP scope
                days_mentioned=len(day_pairs),
                total_mentions=total_mentions,
                directions=directions,
                net_weekly_direction=_weekly_net_direction(directions),
                per_day=per_day,
            )
        )

    ticker_entries.sort(
        key=lambda e: (
            0 if e.in_watchlist else 1,
            -e.days_mentioned,
            -e.total_mentions,
            e.symbol or e.display,
        )
    )

    # === Sector / theme aggregation from key_insights + red_team ===
    sector_day_counts: dict[str, set[Date]] = {}
    sector_total: Counter = Counter()
    theme_day_counts: dict[str, set[Date]] = {}
    theme_total: Counter = Counter()
    for b in bl:
        for ki in b.key_insights:
            for s in ki.sector_tags:
                sector_day_counts.setdefault(s, set()).add(b.date)
                sector_total[s] += 1
            for t in ki.theme_tags:
                theme_day_counts.setdefault(t, set()).add(b.date)
                theme_total[t] += 1
        for rt in b.red_team:
            for s in rt.sector_tags:
                sector_day_counts.setdefault(s, set()).add(b.date)
                sector_total[s] += 1
            for t in rt.theme_tags:
                theme_day_counts.setdefault(t, set()).add(b.date)
                theme_total[t] += 1

    sectors = tuple(
        WeeklySectorEntry(
            sector_slug=slug,
            insight_days=len(days),
            total_insight_mentions=sector_total[slug],
            related_tickers=(),  # P3 MVP: no per-row sector→ticker join
        )
        for slug, days in sorted(sector_day_counts.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    )

    themes = tuple(
        WeeklyThemeEntry(
            theme_slug=slug,
            insight_days=len(days),
            total_insight_mentions=theme_total[slug],
            related_tickers=(),
        )
        for slug, days in sorted(theme_day_counts.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    )

    total_videos = sum(len(b.videos) for b in bl)

    return WeeklyRollup(
        week_start=week_start,
        week_end=week_end,
        daily_briefs_present=present_dates,
        daily_briefs_missing=missing_dates,
        tickers=tuple(ticker_entries),
        sectors=sectors,
        themes=themes,
        total_videos=total_videos,
    )


def render_weekly_brief_markdown(rollup: "WeeklyRollup", *, captured_at) -> str:
    """Render weekly brief markdown document."""
    parts: list[str] = []

    # Frontmatter
    parts.append("---")
    parts.append(f"captured_at: {captured_at.isoformat()}")
    parts.append(f"week_start: {rollup.week_start.isoformat()}")
    parts.append(f"week_end: {rollup.week_end.isoformat()}")
    parts.append(f"daily_briefs_present: {_yaml_inline_list([d.isoformat() for d in rollup.daily_briefs_present])}")
    parts.append(f"daily_briefs_missing: {_yaml_inline_list([d.isoformat() for d in rollup.daily_briefs_missing])}")
    parts.append(f"total_videos: {rollup.total_videos}")
    parts.append(f"sector_slugs_union: {_yaml_inline_list(sorted({s.sector_slug for s in rollup.sectors}))}")
    parts.append(f"theme_slugs_union: {_yaml_inline_list(sorted({t.theme_slug for t in rollup.themes}))}")
    parts.append("source_type: youtube_weekly_brief")
    parts.append("source_url: ''")
    parts.append("tags:")
    parts.append("  - youtube")
    parts.append("  - weekly_brief")
    parts.append("tier: deep")
    parts.append("---")
    parts.append("")

    parts.append(f"# 📅 {rollup.week_start.isoformat()} ~ {rollup.week_end.isoformat()} 주간 시장 브리핑\n")
    parts.append(
        f"처리 영상 {rollup.total_videos}건 · "
        f"정상 brief {len(rollup.daily_briefs_present)}/7일"
        + (f" · 누락 {len(rollup.daily_briefs_missing)}일" if rollup.daily_briefs_missing else "")
        + "\n"
    )

    # Watchlist ticker
    wl_tickers = [t for t in rollup.tickers if t.in_watchlist]
    if wl_tickers:
        parts.append("## 📊 워치리스트 종목 주간 누적\n")
        parts.append("| 종목 | 주간 방향 | 등장 일수 | 영상수 | 일자별 |")
        parts.append("|------|----------|---------|--------|--------|")
        for t in wl_tickers:
            emoji = _DIRECTION_EMOJI.get(t.net_weekly_direction, "")
            label = t.display + (f" ({t.symbol})" if t.symbol else "")
            per_day_str = ", ".join(
                f"{d.date.strftime('%m-%d')} {_DIRECTION_EMOJI.get(d.direction, '')}"
                for d in t.per_day
            )
            parts.append(
                f"| {label} | {emoji} {t.net_weekly_direction} "
                f"| {t.days_mentioned}/7일 | {t.total_mentions} | {per_day_str} |"
            )
        parts.append("")

    # Auto-discovered (≥2 days)
    auto_tickers = [t for t in rollup.tickers if not t.in_watchlist and t.days_mentioned >= 2]
    if auto_tickers:
        parts.append("## 🔍 자동 발견 종목 (주간 ≥2일 등장)\n")
        for t in auto_tickers:
            emoji = _DIRECTION_EMOJI.get(t.net_weekly_direction, "")
            label = t.display + (f" ({t.symbol})" if t.symbol else "")
            parts.append(
                f"- **{label}** {emoji} {t.net_weekly_direction} — "
                f"{t.days_mentioned}일 등장, {t.total_mentions} 영상"
            )
        parts.append("")

    # Sector heatmap
    if rollup.sectors:
        parts.append("## 🎯 Sector 7-day heatmap\n")
        parts.append("| Sector | 등장 일수 | 영상수 | 관련 ticker |")
        parts.append("|--------|----------|--------|------------|")
        for s in rollup.sectors:
            related = ", ".join(s.related_tickers) if s.related_tickers else "—"
            parts.append(
                f"| {s.sector_slug} | {s.insight_days}/7일 | {s.total_insight_mentions} | {related} |"
            )
        parts.append("")

    # Theme heatmap
    if rollup.themes:
        parts.append("## 🎨 Theme 7-day heatmap\n")
        parts.append("| Theme | 등장 일수 | 영상수 | 관련 ticker |")
        parts.append("|-------|----------|--------|------------|")
        for t in rollup.themes:
            related = ", ".join(t.related_tickers) if t.related_tickers else "—"
            parts.append(
                f"| {t.theme_slug} | {t.insight_days}/7일 | {t.total_insight_mentions} | {related} |"
            )
        parts.append("")

    # Missing briefs
    if rollup.daily_briefs_missing:
        parts.append("## 📝 누락된 daily brief\n")
        for d in rollup.daily_briefs_missing:
            parts.append(f"- {d.isoformat()} — `Harness/logs/youtube_market_brief/{d.isoformat()}.log` 확인")
        parts.append("")

    return "\n".join(parts).rstrip() + "\n"


def _weekly_net_direction(directions: tuple) -> "NetDirection":
    """Majority logic. Tie → 혼조."""
    if not directions:
        return "언급만"
    meaningful = [d for d in directions if d != "언급만"]
    if not meaningful:
        return "언급만"
    counts = Counter(meaningful)
    top_dir, top_count = counts.most_common(1)[0]
    if top_count > len(meaningful) / 2:
        return top_dir
    return "혼조"
