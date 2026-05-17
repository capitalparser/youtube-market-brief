from datetime import UTC, datetime

import yaml

from youtube_market_brief.domain.markdown import render_video_markdown
from youtube_market_brief.domain.types import (
    KeyInsight,
    LLMMeta,
    RedTeamItem,
    TickerMention,
    TranscriptSummary,
    VideoAnalysis,
    VideoMeta,
)


def _make_analysis() -> VideoAnalysis:
    v = VideoMeta(
        video_id="abc",
        channel_id="cid",
        channel_name="HK",
        channel_slug="hk",
        title="제목",
        published_at_utc=datetime(2026, 5, 11, tzinfo=UTC),
        url="https://youtu.be/abc",
    )
    s = TranscriptSummary(
        headline_3line=("h1", "h2", "h3"),
        key_insights=(
            KeyInsight(text="i1", sector_tags=("semiconductors",), theme_tags=("hyperscaler_capex",)),
            KeyInsight(text="i2", sector_tags=("financials",), theme_tags=()),
        ),
        red_team=(
            RedTeamItem(text="r1", sector_tags=("semiconductors",), theme_tags=("ai_meltup_bubble",)),
        ),
        chars_used=0,
        was_truncated=False,
    )
    t = TickerMention(
        symbol="005930",
        display="삼성전자",
        in_watchlist=True,
        sector_tag="semiconductors",
        direction="긍정적",
        reasoning="HBM",
        quotes=("...",),
        confidence="high",
    )
    return VideoAnalysis(
        video=v,
        transcript_summary=s,
        tickers=(t,),
        watchlist_hits=("005930",),
        tier="deep",
        tags=("youtube", "hk"),
        llm_meta=LLMMeta(model="test", duration_ms=0),
        generated_at=datetime(2026, 5, 11, tzinfo=UTC),
    )


def _parse_fm(md: str) -> dict:
    assert md.startswith("---\n")
    end = md.index("\n---\n", 4)
    return yaml.safe_load(md[4:end])


def test_frontmatter_contains_insight_sector_tags_union():
    md = render_video_markdown(_make_analysis(), captured_at=datetime(2026, 5, 11, tzinfo=UTC))
    fm = _parse_fm(md)
    assert set(fm["insight_sector_tags"]) == {"semiconductors", "financials"}
    assert set(fm["insight_theme_tags"]) == {"hyperscaler_capex"}


def test_frontmatter_contains_red_team_tags_union():
    md = render_video_markdown(_make_analysis(), captured_at=datetime(2026, 5, 11, tzinfo=UTC))
    fm = _parse_fm(md)
    assert set(fm["red_team_sector_tags"]) == {"semiconductors"}
    assert set(fm["red_team_theme_tags"]) == {"ai_meltup_bubble"}


def test_body_renders_text_only_no_inline_tags():
    md = render_video_markdown(_make_analysis(), captured_at=datetime(2026, 5, 11, tzinfo=UTC))
    body = md.split("\n---\n\n", 1)[1]
    assert "- i1" in body
    assert "- i2" in body
    assert "- r1" in body
    assert "#semiconductors" not in body
    assert "[semiconductors]" not in body


def test_empty_tag_union_yields_empty_list_in_frontmatter():
    a = _make_analysis()
    s = TranscriptSummary(
        headline_3line=("h1", "h2", "h3"),
        key_insights=(KeyInsight(text="i", sector_tags=(), theme_tags=()),),
        red_team=(RedTeamItem(text="r", sector_tags=(), theme_tags=()),),
        chars_used=0,
        was_truncated=False,
    )
    a2 = VideoAnalysis(
        video=a.video,
        transcript_summary=s,
        tickers=a.tickers,
        watchlist_hits=a.watchlist_hits,
        tier=a.tier,
        tags=a.tags,
        llm_meta=a.llm_meta,
        generated_at=a.generated_at,
    )
    md = render_video_markdown(a2, captured_at=datetime(2026, 5, 11, tzinfo=UTC))
    fm = _parse_fm(md)
    assert fm["insight_sector_tags"] == []
    assert fm["insight_theme_tags"] == []
