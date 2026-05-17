import yaml
from datetime import UTC, date, datetime

from youtube_market_brief.domain.daily_brief import render_daily_brief_markdown
from youtube_market_brief.domain.types import (
    DailyBrief,
    KeyInsight,
    LLMMeta,
    RedTeamItem,
    TickerMention,
    TranscriptSummary,
    VideoAnalysis,
    VideoMeta,
)


def _parse_fm(md: str) -> dict:
    """Extract and YAML-parse the frontmatter block from a markdown string."""
    fm_str = md.split("---\n", 1)[1].split("\n---\n", 1)[0]
    return yaml.safe_load(fm_str)


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
    fm = _parse_fm(md)
    assert fm["insight_sector_tags"] == ["financials", "semiconductors"]
    assert fm["insight_theme_tags"] == ["hyperscaler_capex"]
    assert fm["red_team_sector_tags"] == ["energy"]
    assert fm["red_team_theme_tags"] == ["geopolitics_middle_east"]


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
    fm = _parse_fm(md)
    assert fm["insight_sector_tags"] == []
    assert fm["red_team_sector_tags"] == []


def test_daily_rollup_preserves_sector_tag_for_weekly_links():
    from youtube_market_brief.domain.daily_brief import compute_rollup, compute_weekly_rollup

    video = VideoMeta(
        video_id="v1",
        channel_id="UC1",
        channel_name="Channel",
        channel_slug="channel",
        title="Video",
        published_at_utc=datetime(2026, 5, 11, tzinfo=UTC),
        url="https://youtu.be/v1",
    )
    analysis = VideoAnalysis(
        video=video,
        transcript_summary=TranscriptSummary(
            headline_3line=("a", "b", "c"),
            key_insights=(
                KeyInsight(text="semis", sector_tags=("semiconductors",), theme_tags=()),
            ),
            red_team=(),
            chars_used=100,
            was_truncated=False,
        ),
        tickers=(
            TickerMention(
                symbol="NVDA",
                display="NVIDIA",
                in_watchlist=True,
                direction="긍정적",
                reasoning="AI capex",
                quotes=("quote",),
                confidence="high",
                sector_tag="semiconductors",
            ),
        ),
        watchlist_hits=("NVDA",),
        tier="deep",
        tags=("youtube",),
        llm_meta=LLMMeta(model="test", duration_ms=1),
        generated_at=datetime(2026, 5, 11, tzinfo=UTC),
    )
    rollup = compute_rollup((analysis,))
    assert rollup[0].sector_tag == "semiconductors"

    brief = DailyBrief(
        date=date(2026, 5, 11),
        market_read="m",
        key_insights=analysis.transcript_summary.key_insights,
        red_team=(),
        ticker_rollup=rollup,
        videos=(video,),
        llm_meta=LLMMeta(model="test", duration_ms=1),
    )
    weekly = compute_weekly_rollup((brief,), week_start=date(2026, 5, 11))
    assert weekly is not None
    assert weekly.tickers[0].sector_tag == "semiconductors"
    assert weekly.sectors[0].related_tickers == ("NVDA",)
