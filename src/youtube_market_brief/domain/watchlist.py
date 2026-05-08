"""Watchlist alias matching and false-positive guards.

Pure domain — no IO. Used after LLM analysis to (a) filter watchlist hits
to those with substantive evidence (quotes), (b) reconcile aliases /
display names with canonical symbols.
"""

from __future__ import annotations

from collections.abc import Iterable

from youtube_market_brief.domain.types import (
    TickerMention,
    Watchlist,
    WatchlistEntry,
)


def resolve_symbol(mention: TickerMention, watchlist: Watchlist) -> WatchlistEntry | None:
    """Find watchlist entry matching this LLM mention. None if no match."""
    if mention.symbol:
        for e in watchlist.entries:
            if e.symbol == mention.symbol:
                return e
    candidate = mention.display.strip()
    if not candidate:
        return None
    for e in watchlist.entries:
        if candidate == e.name_ko:
            return e
        if e.name_en and candidate == e.name_en:
            return e
        if candidate in e.aliases:
            return e
    return None


def filter_watchlist_hits(
    mentions: Iterable[TickerMention],
    watchlist: Watchlist,
    *,
    require_quote: bool = True,
) -> tuple[str, ...]:
    """Compute watchlist_hits symbols from LLM mentions.

    Filtering rules:
    - direction "언급만" → excluded (mere mention without analytical content)
    - require_quote=True (default) → must have at least one non-empty quote
    - watchlist resolution required (alias/display match)
    """
    hits: list[str] = []
    for m in mentions:
        if m.direction == "언급만":
            continue
        if require_quote and not any(q.strip() for q in m.quotes):
            continue
        entry = resolve_symbol(m, watchlist)
        if entry is None:
            continue
        if entry.symbol not in hits:
            hits.append(entry.symbol)
    return tuple(hits)


def annotate_in_watchlist(
    mentions: Iterable[TickerMention], watchlist: Watchlist
) -> tuple[TickerMention, ...]:
    """Re-stamp `in_watchlist` flag and canonical `symbol` on LLM mentions.

    LLM may have set in_watchlist incorrectly; we reconcile against the
    actual config. `symbol` becomes the watchlist canonical when a match
    is found.
    """
    out: list[TickerMention] = []
    for m in mentions:
        entry = resolve_symbol(m, watchlist)
        if entry is not None:
            out.append(
                TickerMention(
                    symbol=entry.symbol,
                    display=m.display,
                    in_watchlist=True,
                    direction=m.direction,
                    reasoning=m.reasoning,
                    quotes=m.quotes,
                    confidence=m.confidence,
                )
            )
        else:
            out.append(
                TickerMention(
                    symbol=m.symbol,
                    display=m.display,
                    in_watchlist=False,
                    direction=m.direction,
                    reasoning=m.reasoning,
                    quotes=m.quotes,
                    confidence=m.confidence,
                )
            )
    return tuple(out)
