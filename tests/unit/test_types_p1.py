import dataclasses

import pytest

from youtube_market_brief.domain.types import (
    KeyInsight,
    RedTeamItem,
    TickerMention,
    TranscriptSummary,
    WatchlistEntry,
)


def test_key_insight_dataclass_shape():
    ki = KeyInsight(
        text="hi", sector_tags=("semiconductors",), theme_tags=()
    )
    assert ki.text == "hi"
    assert ki.sector_tags == ("semiconductors",)
    assert ki.theme_tags == ()


def test_key_insight_is_frozen():
    ki = KeyInsight(text="x", sector_tags=(), theme_tags=())
    with pytest.raises(dataclasses.FrozenInstanceError):
        ki.text = "y"  # type: ignore[misc]


def test_red_team_item_dataclass_shape():
    rt = RedTeamItem(
        text="caution", sector_tags=("financials",), theme_tags=("us_fiscal_debt",)
    )
    assert rt.text == "caution"
    assert rt.sector_tags == ("financials",)
    assert rt.theme_tags == ("us_fiscal_debt",)


def test_red_team_item_is_frozen():
    rt = RedTeamItem(text="x", sector_tags=(), theme_tags=())
    with pytest.raises(dataclasses.FrozenInstanceError):
        rt.text = "y"  # type: ignore[misc]


def test_watchlist_entry_has_sector_field():
    e = WatchlistEntry(
        symbol="005930",
        market="KOSPI",
        name_ko="삼성전자",
        sector="semiconductors",
    )
    assert e.sector == "semiconductors"


def test_watchlist_entry_sector_defaults_to_empty():
    e = WatchlistEntry(symbol="005930", market="KOSPI", name_ko="삼성전자")
    assert e.sector == ""


def test_ticker_mention_has_sector_tag_field():
    m = TickerMention(
        symbol="005930",
        display="삼성전자",
        in_watchlist=True,
        sector_tag="semiconductors",
        direction="긍정적",
        reasoning="HBM3E",
        quotes=(),
        confidence="high",
    )
    assert m.sector_tag == "semiconductors"


def test_ticker_mention_sector_tag_can_be_none():
    m = TickerMention(
        symbol=None,
        display="(unknown)",
        in_watchlist=False,
        sector_tag=None,
        direction="언급만",
        reasoning="",
        quotes=(),
        confidence="low",
    )
    assert m.sector_tag is None


def test_transcript_summary_uses_key_insight_objects():
    s = TranscriptSummary(
        headline_3line=("a", "b", "c"),
        key_insights=(KeyInsight(text="i1", sector_tags=(), theme_tags=()),),
        red_team=(RedTeamItem(text="r1", sector_tags=(), theme_tags=()),),
        chars_used=0,
        was_truncated=False,
    )
    assert s.key_insights[0].text == "i1"
    assert isinstance(s.red_team[0], RedTeamItem)
