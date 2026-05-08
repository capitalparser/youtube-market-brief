from datetime import UTC, datetime

from youtube_market_brief.domain.daily_brief import compute_rollup
from youtube_market_brief.domain.types import (
    LLMMeta,
    TickerMention,
    TranscriptSummary,
    VideoAnalysis,
    VideoMeta,
)


def _video(video_id: str) -> VideoMeta:
    return VideoMeta(
        video_id=video_id,
        channel_id="UCabc",
        channel_name="ch",
        channel_slug="ch",
        title="t",
        published_at_utc=datetime(2026, 5, 7, 0, 0, tzinfo=UTC),
        url=f"https://youtu.be/{video_id}",
    )


def _analysis(video_id: str, mentions: tuple[TickerMention, ...]) -> VideoAnalysis:
    return VideoAnalysis(
        video=_video(video_id),
        transcript_summary=TranscriptSummary(
            headline_3line=("a", "b", "c"),
            key_insights=("k1", "k2", "k3"),
            red_team=("r1",),
            chars_used=100,
            was_truncated=False,
        ),
        tickers=mentions,
        watchlist_hits=tuple(m.symbol for m in mentions if m.in_watchlist and m.symbol),
        tier="deep" if any(m.in_watchlist for m in mentions) else "light",
        tags=(),
        llm_meta=LLMMeta(model="sonnet", duration_ms=10),
        generated_at=datetime(2026, 5, 7, 0, 0, tzinfo=UTC),
    )


def _m(symbol, display, in_watchlist, direction, reasoning="r"):
    return TickerMention(
        symbol=symbol,
        display=display,
        in_watchlist=in_watchlist,
        direction=direction,
        reasoning=reasoning,
        quotes=("q",),
        confidence="medium",
    )


def test_rollup_all_same_direction():
    a1 = _analysis("v1", (_m("005930", "삼성전자", True, "긍정적"),))
    a2 = _analysis("v2", (_m("005930", "삼성전자", True, "긍정적"),))
    rollups = compute_rollup([a1, a2])
    assert len(rollups) == 1
    assert rollups[0].net_direction == "긍정적"
    assert rollups[0].mention_count == 2


def test_rollup_mixed_is_혼조():
    a1 = _analysis("v1", (_m("005930", "삼성전자", True, "긍정적"),))
    a2 = _analysis("v2", (_m("005930", "삼성전자", True, "긍정적"),))
    a3 = _analysis("v3", (_m("005930", "삼성전자", True, "부정적"),))
    rollups = compute_rollup([a1, a2, a3])
    assert rollups[0].net_direction == "혼조"
    assert rollups[0].mention_count == 3


def test_rollup_언급만_only_returns_언급만():
    a1 = _analysis("v1", (_m("005930", "삼성전자", True, "언급만"),))
    rollups = compute_rollup([a1])
    assert rollups[0].net_direction == "언급만"


def test_rollup_sorts_watchlist_first():
    wl = _m("005930", "삼성전자", True, "긍정적")
    auto = _m(None, "어떤종목", False, "긍정적")
    a = _analysis("v1", (auto, wl))
    rollups = compute_rollup([a])
    assert rollups[0].in_watchlist is True
    assert rollups[1].in_watchlist is False
