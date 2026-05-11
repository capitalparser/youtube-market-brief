"""Weekly aggregation pipeline — loads .analysis.json sidecars, computes weekly rollup,
writes vault MD + .analysis.json sidecar, sends Telegram.
"""

from __future__ import annotations

import json
import logging
from datetime import date as Date, datetime, timedelta
from pathlib import Path

from youtube_market_brief.domain.daily_brief import (
    compute_weekly_rollup,
    render_weekly_brief_markdown,
)
from youtube_market_brief.domain.types import (
    DailyBrief,
    KeyInsight,
    LLMMeta,
    RedTeamItem,
    TickerRollup,
    TickerRollupVideoEntry,
    TickerRollupVideoEntry,
    VideoMeta,
    WeeklyRollup,
)

log = logging.getLogger(__name__)


def last_monday(today: Date) -> Date:
    """Most recent Monday on or before `today`."""
    return today - timedelta(days=today.weekday())


def load_weekly_briefs(*, vault_daily_root: Path, week_start: Date) -> list[DailyBrief]:
    """Load up to 7 .analysis.json sidecars from vault_daily_root for the target week.

    Missing days are silently skipped (warning logged). Out-of-range files are
    ignored (only week_start ~ week_start+6 considered).
    """
    if not vault_daily_root.exists():
        return []
    briefs: list[DailyBrief] = []
    for i in range(7):
        d = week_start + timedelta(days=i)
        sidecar = vault_daily_root / f"{d.isoformat()}_brief.analysis.json"
        if not sidecar.exists():
            log.warning("daily brief sidecar missing for %s", d)
            continue
        briefs.append(_deserialize_brief(sidecar, d))
    return briefs


def _deserialize_brief(sidecar_path: Path, target_date: Date) -> DailyBrief:
    """Inverse of write_daily_brief_md's sidecar serialization."""
    data = json.loads(sidecar_path.read_text(encoding="utf-8"))
    key_insights = tuple(
        KeyInsight(
            text=str(ki.get("text", "")),
            sector_tags=tuple(ki.get("sector_tags") or []),
            theme_tags=tuple(ki.get("theme_tags") or []),
        )
        for ki in (data.get("key_insights") or [])
        if isinstance(ki, dict)
    )
    red_team = tuple(
        RedTeamItem(
            text=str(rt.get("text", "")),
            sector_tags=tuple(rt.get("sector_tags") or []),
            theme_tags=tuple(rt.get("theme_tags") or []),
        )
        for rt in (data.get("red_team") or [])
        if isinstance(rt, dict)
    )
    ticker_rollup = tuple(
        TickerRollup(
            symbol=r.get("symbol"),
            display=str(r.get("display", "")),
            in_watchlist=bool(r.get("in_watchlist")),
            net_direction=r.get("net_direction", "언급만"),
            mention_count=int(r.get("mention_count", 0)),
            per_video=tuple(
                TickerRollupVideoEntry(
                    video_id=str(e.get("video_id", "")),
                    direction=e.get("direction", "언급만"),
                    one_line_reason=str(e.get("one_line_reason", "")),
                )
                for e in (r.get("per_video") or [])
                if isinstance(e, dict)
            ),
        )
        for r in (data.get("ticker_rollup") or [])
        if isinstance(r, dict)
    )
    videos = tuple(
        VideoMeta(
            video_id=str(v.get("video_id", "")),
            channel_id="",
            channel_name="",
            channel_slug=str(v.get("channel_slug", "")),
            title=str(v.get("title", "")),
            published_at_utc=datetime.fromisoformat("2026-01-01T00:00:00+00:00"),
            url=str(v.get("url", "")),
        )
        for v in (data.get("videos") or [])
        if isinstance(v, dict)
    )
    llm_meta_data = data.get("llm_meta") or {}
    return DailyBrief(
        date=target_date,
        market_read=str(data.get("market_read", "")),
        key_insights=key_insights,
        red_team=red_team,
        ticker_rollup=ticker_rollup,
        videos=videos,
        llm_meta=LLMMeta(
            model=str(llm_meta_data.get("model", "")),
            duration_ms=int(llm_meta_data.get("duration_ms", 0)),
            claude_session_id=llm_meta_data.get("claude_session_id"),
        ),
    )


def aggregate_weekly(
    *, week_start: Date, vault_daily_root: Path
) -> WeeklyRollup | None:
    """Load briefs + compute weekly rollup. None if zero briefs found."""
    briefs = load_weekly_briefs(vault_daily_root=vault_daily_root, week_start=week_start)
    if not briefs:
        return None
    return compute_weekly_rollup(briefs, week_start=week_start)


def write_weekly_md(
    rollup: WeeklyRollup,
    *,
    vault_weekly_root: Path,
    captured_at: datetime,
) -> Path:
    """Write weekly brief MD + .analysis.json sidecar. Returns MD path."""
    vault_weekly_root.mkdir(parents=True, exist_ok=True)
    out = vault_weekly_root / f"{rollup.week_start.isoformat()}_weekly.md"
    body = render_weekly_brief_markdown(rollup, captured_at=captured_at)
    out.write_text(body, encoding="utf-8")
    log.info("wrote weekly brief MD: %s", out)

    sidecar = out.with_suffix(".analysis.json")
    sidecar_data = {
        "week_start": rollup.week_start.isoformat(),
        "week_end": rollup.week_end.isoformat(),
        "captured_at": captured_at.isoformat(),
        "daily_briefs_present": [d.isoformat() for d in rollup.daily_briefs_present],
        "daily_briefs_missing": [d.isoformat() for d in rollup.daily_briefs_missing],
        "total_videos": rollup.total_videos,
        "tickers": [
            {
                "symbol": t.symbol, "display": t.display, "in_watchlist": t.in_watchlist,
                "sector_tag": t.sector_tag,
                "days_mentioned": t.days_mentioned, "total_mentions": t.total_mentions,
                "directions": list(t.directions),
                "net_weekly_direction": t.net_weekly_direction,
                "per_day": [
                    {"date": d.date.isoformat(), "direction": d.direction, "mention_count": d.mention_count}
                    for d in t.per_day
                ],
            }
            for t in rollup.tickers
        ],
        "sectors": [
            {"sector_slug": s.sector_slug, "insight_days": s.insight_days,
             "total_insight_mentions": s.total_insight_mentions,
             "related_tickers": list(s.related_tickers)}
            for s in rollup.sectors
        ],
        "themes": [
            {"theme_slug": t.theme_slug, "insight_days": t.insight_days,
             "total_insight_mentions": t.total_insight_mentions,
             "related_tickers": list(t.related_tickers)}
            for t in rollup.themes
        ],
    }
    sidecar.write_text(
        json.dumps(sidecar_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log.info("wrote weekly brief sidecar: %s", sidecar)
    return out
