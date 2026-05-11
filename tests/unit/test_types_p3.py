import dataclasses
from datetime import date

import pytest

from youtube_market_brief.domain.types import (
    WeeklyRollup,
    WeeklySectorEntry,
    WeeklyThemeEntry,
    WeeklyTickerDayEntry,
    WeeklyTickerEntry,
)


def test_weekly_ticker_day_entry_shape():
    e = WeeklyTickerDayEntry(date=date(2026, 5, 5), direction="긍정적", mention_count=2)
    assert e.date == date(2026, 5, 5)
    assert e.direction == "긍정적"
    assert e.mention_count == 2


def test_weekly_ticker_entry_shape():
    e = WeeklyTickerEntry(
        symbol="005930",
        display="삼성전자",
        in_watchlist=True,
        sector_tag="semiconductors",
        days_mentioned=5,
        total_mentions=8,
        directions=("긍정적", "혼조", "부정적"),
        net_weekly_direction="부정적",
        per_day=(),
    )
    assert e.days_mentioned == 5
    assert e.net_weekly_direction == "부정적"


def test_weekly_sector_entry_shape():
    e = WeeklySectorEntry(
        sector_slug="semiconductors",
        insight_days=7,
        total_insight_mentions=15,
        related_tickers=("005930", "000660", "NVDA"),
    )
    assert e.sector_slug == "semiconductors"
    assert e.insight_days == 7


def test_weekly_theme_entry_shape():
    e = WeeklyThemeEntry(
        theme_slug="hyperscaler_capex",
        insight_days=5,
        total_insight_mentions=12,
        related_tickers=("NVDA", "MSFT"),
    )
    assert e.theme_slug == "hyperscaler_capex"


def test_weekly_rollup_shape():
    r = WeeklyRollup(
        week_start=date(2026, 5, 5),
        week_end=date(2026, 5, 11),
        daily_briefs_present=(date(2026, 5, 5), date(2026, 5, 6)),
        daily_briefs_missing=(date(2026, 5, 7),),
        tickers=(),
        sectors=(),
        themes=(),
        total_videos=10,
    )
    assert r.week_start == date(2026, 5, 5)
    assert r.total_videos == 10


def test_weekly_rollup_is_frozen():
    r = WeeklyRollup(
        week_start=date(2026, 5, 5), week_end=date(2026, 5, 11),
        daily_briefs_present=(), daily_briefs_missing=(),
        tickers=(), sectors=(), themes=(), total_videos=0,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.total_videos = 1  # type: ignore[misc]
