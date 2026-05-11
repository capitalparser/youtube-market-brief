"""Watchlist alias matching and false-positive guards.

Pure domain — no IO. Used after LLM analysis to (a) filter watchlist hits
to those with substantive evidence (quotes), (b) reconcile aliases /
display names with canonical symbols.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable

from youtube_market_brief.domain.types import (
    TickerMention,
    Watchlist,
    WatchlistEntry,
)

log = logging.getLogger(__name__)


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
    """Re-stamp `in_watchlist`, canonical `symbol`, `sector_tag` on LLM mentions.

    sector_tag 결정:
    - watchlist 매칭되면 WatchlistEntry.sector로 *덮어쓰기* (watchlist 우선).
      단 WatchlistEntry.sector가 빈 문자열이면 LLM 값 보존.
    - watchlist 매칭 안 되면 LLM 출력 sector_tag 그대로 사용.
    """
    out: list[TickerMention] = []
    for m in mentions:
        entry = resolve_symbol(m, watchlist)
        if entry is not None:
            sector_tag = entry.sector if entry.sector else m.sector_tag
            if entry.sector and m.sector_tag and entry.sector != m.sector_tag:
                log.warning(
                    "ticker %s sector conflict: llm=%s watchlist=%s — using watchlist",
                    entry.symbol, m.sector_tag, entry.sector,
                )
            out.append(
                TickerMention(
                    symbol=entry.symbol,
                    display=m.display,
                    in_watchlist=True,
                    sector_tag=sector_tag,
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
                    sector_tag=m.sector_tag,
                    direction=m.direction,
                    reasoning=m.reasoning,
                    quotes=m.quotes,
                    confidence=m.confidence,
                )
            )
    return tuple(out)
