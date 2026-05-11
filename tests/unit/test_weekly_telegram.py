from datetime import date

from youtube_market_brief.domain.telegram_format import format_weekly_brief
from youtube_market_brief.domain.types import (
    WeeklyRollup,
    WeeklySectorEntry,
    WeeklyThemeEntry,
    WeeklyTickerEntry,
)


def _make_rollup() -> WeeklyRollup:
    return WeeklyRollup(
        week_start=date(2026, 5, 5),
        week_end=date(2026, 5, 11),
        daily_briefs_present=(date(2026, 5, 5),),
        daily_briefs_missing=(date(2026, 5, 6),),
        tickers=(
            WeeklyTickerEntry(
                symbol="005930", display="삼성전자", in_watchlist=True, sector_tag=None,
                days_mentioned=5, total_mentions=8,
                directions=("긍정적",) * 5, net_weekly_direction="긍정적",
                per_day=(),
            ),
        ),
        sectors=(
            WeeklySectorEntry(
                sector_slug="semiconductors", insight_days=5,
                total_insight_mentions=10, related_tickers=("005930",),
            ),
        ),
        themes=(),
        total_videos=12,
    )


def test_format_weekly_brief_includes_header():
    out = format_weekly_brief(_make_rollup(), vault_md_path_relative="00_Wiki/youtube/_weekly/x.md")
    assert "2026-05-05" in out
    assert "2026-05-11" in out


def test_format_weekly_brief_includes_ticker():
    out = format_weekly_brief(_make_rollup(), vault_md_path_relative="x.md")
    assert "삼성전자" in out
    assert "5/7" in out or "5일" in out


def test_format_weekly_brief_escapes_html():
    rollup = WeeklyRollup(
        week_start=date(2026, 5, 5), week_end=date(2026, 5, 11),
        daily_briefs_present=(), daily_briefs_missing=(),
        tickers=(
            WeeklyTickerEntry(
                symbol="X", display="A & B <X>", in_watchlist=True, sector_tag=None,
                days_mentioned=1, total_mentions=1,
                directions=("긍정적",), net_weekly_direction="긍정적",
                per_day=(),
            ),
        ),
        sectors=(), themes=(), total_videos=0,
    )
    out = format_weekly_brief(rollup, vault_md_path_relative="x & y.md")
    assert "&amp;" in out
    assert "&lt;" in out


def test_format_weekly_brief_includes_sector_when_present():
    out = format_weekly_brief(_make_rollup(), vault_md_path_relative="x.md")
    assert "semiconductors" in out


def test_notify_target_literal_includes_weekly():
    """NotifyTarget Literal type should include 'weekly'."""
    from typing import get_args
    from youtube_market_brief.domain.types import NotifyTarget
    args = get_args(NotifyTarget)
    assert "weekly" in args
