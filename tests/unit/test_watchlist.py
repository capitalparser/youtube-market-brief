from youtube_market_brief.domain.types import (
    TickerMention,
    Watchlist,
    WatchlistEntry,
)
from youtube_market_brief.domain.watchlist import (
    annotate_in_watchlist,
    filter_watchlist_hits,
    resolve_symbol,
)

WATCHLIST = Watchlist(
    entries=(
        WatchlistEntry(
            symbol="005930",
            market="KOSPI",
            name_ko="삼성전자",
            name_en="Samsung Electronics",
            aliases=("삼전",),
        ),
        WatchlistEntry(
            symbol="NVDA",
            market="NASDAQ",
            name_ko="엔비디아",
            name_en="NVIDIA",
            aliases=("엔비",),
        ),
    )
)


def _mention(symbol=None, display="", direction="중립", quotes=("의미있는 인용",)):
    return TickerMention(
        symbol=symbol,
        display=display,
        in_watchlist=False,
        direction=direction,
        reasoning="reason",
        quotes=quotes,
        confidence="medium",
    )


def test_resolve_by_symbol():
    m = _mention(symbol="005930", display="아무거나")
    assert resolve_symbol(m, WATCHLIST).symbol == "005930"


def test_resolve_by_name_ko():
    m = _mention(display="삼성전자")
    assert resolve_symbol(m, WATCHLIST).symbol == "005930"


def test_resolve_by_alias():
    m = _mention(display="엔비")
    assert resolve_symbol(m, WATCHLIST).symbol == "NVDA"


def test_resolve_unknown_returns_none():
    m = _mention(display="모르는종목")
    assert resolve_symbol(m, WATCHLIST) is None


def test_filter_excludes_언급만_direction():
    m = _mention(display="삼성전자", direction="언급만")
    assert filter_watchlist_hits([m], WATCHLIST) == ()


def test_filter_excludes_no_quote():
    m = _mention(display="삼성전자", direction="긍정적", quotes=())
    assert filter_watchlist_hits([m], WATCHLIST) == ()


def test_filter_includes_solid_hit():
    m = _mention(display="삼성전자", direction="긍정적", quotes=("실적 호조",))
    assert filter_watchlist_hits([m], WATCHLIST) == ("005930",)


def test_annotate_sets_canonical_symbol_and_flag():
    m = _mention(display="삼전", direction="긍정적", quotes=("alias 매칭",))
    out = annotate_in_watchlist((m,), WATCHLIST)
    assert out[0].symbol == "005930"
    assert out[0].in_watchlist is True


def test_annotate_clears_flag_for_unknown():
    m = TickerMention(
        symbol=None,
        display="모르는종목",
        in_watchlist=True,  # LLM hallucination
        direction="중립",
        reasoning="r",
        quotes=("q",),
        confidence="low",
    )
    out = annotate_in_watchlist((m,), WATCHLIST)
    assert out[0].in_watchlist is False
