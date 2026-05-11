from datetime import UTC, date, datetime

from youtube_market_brief.domain.daily_brief import render_daily_brief_markdown
from youtube_market_brief.domain.types import (
    DailyBrief,
    KeyInsight,
    LLMMeta,
    RedTeamItem,
)


def test_daily_brief_md_frontmatter_aggregates_insight_sectors():
    brief = DailyBrief(
        date=date(2026, 5, 11),
        market_read="m",
        key_insights=(
            KeyInsight(text="i1", sector_tags=("semiconductors",), theme_tags=("hyperscaler_capex",)),
            KeyInsight(text="i2", sector_tags=("financials",), theme_tags=()),
        ),
        red_team=(RedTeamItem(text="r1", sector_tags=("energy",), theme_tags=("geopolitics_middle_east",)),),
        ticker_rollup=(),
        videos=(),
        llm_meta=LLMMeta(model="t", duration_ms=0),
    )
    md = render_daily_brief_markdown(brief, captured_at=datetime(2026, 5, 11, tzinfo=UTC))
    assert "insight_sector_tags: ['financials', 'semiconductors']" in md
    assert "insight_theme_tags: ['hyperscaler_capex']" in md
    assert "red_team_sector_tags: ['energy']" in md
    assert "red_team_theme_tags: ['geopolitics_middle_east']" in md


def test_daily_brief_md_body_renders_text_only():
    brief = DailyBrief(
        date=date(2026, 5, 11),
        market_read="m",
        key_insights=(KeyInsight(text="인사이트", sector_tags=(), theme_tags=()),),
        red_team=(RedTeamItem(text="레드팀", sector_tags=(), theme_tags=()),),
        ticker_rollup=(),
        videos=(),
        llm_meta=LLMMeta(model="t", duration_ms=0),
    )
    md = render_daily_brief_markdown(brief, captured_at=datetime(2026, 5, 11, tzinfo=UTC))
    assert "- 인사이트" in md
    assert "- 레드팀" in md
    assert "#semiconductors" not in md


def test_daily_brief_md_empty_tag_union_yields_empty_lists():
    brief = DailyBrief(
        date=date(2026, 5, 11),
        market_read="m",
        key_insights=(KeyInsight(text="i", sector_tags=(), theme_tags=()),),
        red_team=(RedTeamItem(text="r", sector_tags=(), theme_tags=()),),
        ticker_rollup=(),
        videos=(),
        llm_meta=LLMMeta(model="t", duration_ms=0),
    )
    md = render_daily_brief_markdown(brief, captured_at=datetime(2026, 5, 11, tzinfo=UTC))
    assert "insight_sector_tags: []" in md
    assert "red_team_sector_tags: []" in md
