from datetime import date, datetime, UTC

import pytest

from youtube_market_brief.domain.daily_brief import compute_weekly_rollup
from youtube_market_brief.domain.types import (
    DailyBrief,
    KeyInsight,
    LLMMeta,
    RedTeamItem,
    TickerRollup,
    TickerRollupVideoEntry,
    VideoMeta,
)


def _make_brief(d: date, *, ticker_rollups=(), key_insights=(), red_team=(), videos=()) -> DailyBrief:
    return DailyBrief(
        date=d,
        market_read="m",
        key_insights=key_insights,
        red_team=red_team,
        ticker_rollup=ticker_rollups,
        videos=videos,
        llm_meta=LLMMeta(model="t", duration_ms=0),
    )


def _vid(vid: str) -> VideoMeta:
    return VideoMeta(
        video_id=vid, channel_id="c", channel_name="ch",
        channel_slug="ch", title="t",
        published_at_utc=datetime(2026, 5, 5, tzinfo=UTC),
        url=f"https://youtu.be/{vid}",
    )


def test_compute_weekly_rollup_empty_returns_none():
    assert compute_weekly_rollup([], week_start=date(2026, 5, 5)) is None


def test_compute_weekly_rollup_single_brief_marks_missing():
    b = _make_brief(date(2026, 5, 5))
    r = compute_weekly_rollup([b], week_start=date(2026, 5, 5))
    assert r is not None
    assert r.week_start == date(2026, 5, 5)
    assert r.week_end == date(2026, 5, 11)
    assert r.daily_briefs_present == (date(2026, 5, 5),)
    assert len(r.daily_briefs_missing) == 6


def test_compute_weekly_rollup_aggregates_ticker_across_days():
    """삼성전자: 5/5 긍정적(1mc), 5/6 부정적(2mc) → 2 days, 3 mentions, 혼조."""
    tr_55 = TickerRollup(
        symbol="005930", display="삼성전자", in_watchlist=True,
        net_direction="긍정적", mention_count=1,
        per_video=(TickerRollupVideoEntry(video_id="v1", direction="긍정적", one_line_reason="r"),),
    )
    tr_56 = TickerRollup(
        symbol="005930", display="삼성전자", in_watchlist=True,
        net_direction="부정적", mention_count=2,
        per_video=(
            TickerRollupVideoEntry(video_id="v2", direction="부정적", one_line_reason="r"),
            TickerRollupVideoEntry(video_id="v3", direction="부정적", one_line_reason="r"),
        ),
    )
    briefs = [
        _make_brief(date(2026, 5, 5), ticker_rollups=(tr_55,)),
        _make_brief(date(2026, 5, 6), ticker_rollups=(tr_56,)),
    ]
    r = compute_weekly_rollup(briefs, week_start=date(2026, 5, 5))
    assert len(r.tickers) == 1
    e = r.tickers[0]
    assert e.symbol == "005930"
    assert e.days_mentioned == 2
    assert e.total_mentions == 3
    assert e.net_weekly_direction == "혼조"


def test_compute_weekly_rollup_majority_direction():
    """5 긍정 + 2 부정 → 긍정적."""
    def tr(direction):
        return TickerRollup(
            symbol="NVDA", display="NVDA", in_watchlist=True,
            net_direction=direction, mention_count=1, per_video=(),
        )
    briefs = [
        _make_brief(date(2026, 5, 5), ticker_rollups=(tr("긍정적"),)),
        _make_brief(date(2026, 5, 6), ticker_rollups=(tr("긍정적"),)),
        _make_brief(date(2026, 5, 7), ticker_rollups=(tr("긍정적"),)),
        _make_brief(date(2026, 5, 8), ticker_rollups=(tr("긍정적"),)),
        _make_brief(date(2026, 5, 9), ticker_rollups=(tr("긍정적"),)),
        _make_brief(date(2026, 5, 10), ticker_rollups=(tr("부정적"),)),
        _make_brief(date(2026, 5, 11), ticker_rollups=(tr("부정적"),)),
    ]
    r = compute_weekly_rollup(briefs, week_start=date(2026, 5, 5))
    e = r.tickers[0]
    assert e.days_mentioned == 7
    assert e.net_weekly_direction == "긍정적"


def test_compute_weekly_rollup_tie_returns_mixed():
    """3 긍정 + 3 부정 + 1 중립 → 혼조."""
    def tr(d):
        return TickerRollup(
            symbol="X", display="X", in_watchlist=False, net_direction=d,
            mention_count=1, per_video=(),
        )
    briefs = [
        _make_brief(date(2026, 5, 5), ticker_rollups=(tr("긍정적"),)),
        _make_brief(date(2026, 5, 6), ticker_rollups=(tr("긍정적"),)),
        _make_brief(date(2026, 5, 7), ticker_rollups=(tr("긍정적"),)),
        _make_brief(date(2026, 5, 8), ticker_rollups=(tr("부정적"),)),
        _make_brief(date(2026, 5, 9), ticker_rollups=(tr("부정적"),)),
        _make_brief(date(2026, 5, 10), ticker_rollups=(tr("부정적"),)),
        _make_brief(date(2026, 5, 11), ticker_rollups=(tr("중립"),)),
    ]
    r = compute_weekly_rollup(briefs, week_start=date(2026, 5, 5))
    assert r.tickers[0].net_weekly_direction == "혼조"


def test_compute_weekly_rollup_sector_aggregation():
    """sector_tags: 5/5 [semi], 5/6 [semi, fin] → semi 2 days, fin 1 day."""
    briefs = [
        _make_brief(date(2026, 5, 5), key_insights=(
            KeyInsight(text="i1", sector_tags=("semiconductors",), theme_tags=()),
        )),
        _make_brief(date(2026, 5, 6), key_insights=(
            KeyInsight(text="i2", sector_tags=("semiconductors", "financials"), theme_tags=()),
        )),
    ]
    r = compute_weekly_rollup(briefs, week_start=date(2026, 5, 5))
    by_slug = {s.sector_slug: s for s in r.sectors}
    assert by_slug["semiconductors"].insight_days == 2
    assert by_slug["financials"].insight_days == 1


def test_compute_weekly_rollup_total_videos():
    briefs = [
        _make_brief(date(2026, 5, 5), videos=(_vid("v1"),)),
        _make_brief(date(2026, 5, 6), videos=(_vid("v2"), _vid("v3"))),
    ]
    r = compute_weekly_rollup(briefs, week_start=date(2026, 5, 5))
    assert r.total_videos == 3


def test_compute_weekly_rollup_filters_out_of_range():
    """Briefs outside week_start..week_start+6 should be silently filtered."""
    briefs = [
        _make_brief(date(2026, 5, 5)),
        _make_brief(date(2026, 4, 30)),  # out of range
        _make_brief(date(2026, 5, 12)),  # out of range
    ]
    r = compute_weekly_rollup(briefs, week_start=date(2026, 5, 5))
    assert r.daily_briefs_present == (date(2026, 5, 5),)
