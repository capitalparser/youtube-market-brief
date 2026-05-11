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


def _mention(symbol=None, display="", direction="중립", quotes=("의미있는 인용",), sector_tag=None):
    return TickerMention(
        symbol=symbol,
        display=display,
        in_watchlist=False,
        sector_tag=sector_tag,
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
        sector_tag=None,
        direction="중립",
        reasoning="r",
        quotes=("q",),
        confidence="low",
    )
    out = annotate_in_watchlist((m,), WATCHLIST)
    assert out[0].in_watchlist is False


def test_load_watchlist_parses_sector_field(tmp_path):
    from youtube_market_brief.config import load_watchlist
    p = tmp_path / "wl.yaml"
    p.write_text(
        "tickers:\n"
        "  - symbol: '005930'\n"
        "    market: KOSPI\n"
        "    name_ko: 삼성전자\n"
        "    sector: semiconductors\n",
        encoding="utf-8",
    )
    wl = load_watchlist(p)
    assert wl.entries[0].sector == "semiconductors"


def test_load_watchlist_empty_sector_when_missing(tmp_path):
    from youtube_market_brief.config import load_watchlist
    p = tmp_path / "wl.yaml"
    p.write_text(
        "tickers:\n"
        "  - symbol: '005930'\n"
        "    market: KOSPI\n"
        "    name_ko: 삼성전자\n",
        encoding="utf-8",
    )
    wl = load_watchlist(p)
    assert wl.entries[0].sector == ""


def test_annotate_fills_sector_from_watchlist_when_present():
    """watchlist entry에 sector가 있으면 LLM sector_tag를 덮어씀."""
    wl = Watchlist(
        entries=(
            WatchlistEntry(
                symbol="005930",
                market="KOSPI",
                name_ko="삼성전자",
                name_en="Samsung Electronics",
                sector="semiconductors",
                aliases=("삼전",),
            ),
        )
    )
    m = TickerMention(
        symbol="005930",
        display="삼성전자",
        in_watchlist=False,
        sector_tag="tech_hardware",  # LLM got it wrong
        direction="긍정적",
        reasoning="reason",
        quotes=("실적 호조",),
        confidence="medium",
    )
    out = annotate_in_watchlist((m,), wl)
    assert out[0].sector_tag == "semiconductors"


def test_annotate_preserves_llm_sector_when_watchlist_sector_empty():
    """watchlist entry sector가 빈 문자열이면 LLM sector_tag 보존."""
    wl = Watchlist(
        entries=(
            WatchlistEntry(
                symbol="005930",
                market="KOSPI",
                name_ko="삼성전자",
                name_en="Samsung Electronics",
                sector="",  # not set
                aliases=(),
            ),
        )
    )
    m = TickerMention(
        symbol="005930",
        display="삼성전자",
        in_watchlist=False,
        sector_tag="semiconductors",
        direction="긍정적",
        reasoning="reason",
        quotes=("강한 수요",),
        confidence="high",
    )
    out = annotate_in_watchlist((m,), wl)
    assert out[0].sector_tag == "semiconductors"
