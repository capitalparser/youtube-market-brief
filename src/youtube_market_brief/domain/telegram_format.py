"""Telegram message formatting (3-block: 핵심 인사이트 + 레드팀 + 종목 영향) and chunking.

Telegram Bot API limit: 4096 chars per message. We use a soft cap of 4000 for
safety (emoji are multibyte and we want room for the (n/m) suffix).
"""

from __future__ import annotations

from collections.abc import Iterable

from youtube_market_brief.domain.types import (
    DailyBrief,
    TickerMention,
    TickerRollup,
    VideoAnalysis,
)

SOFT_CAP = 4000

_DIRECTION_EMOJI = {
    "긍정적": "🟢",
    "중립": "⚪",
    "부정적": "🔴",
    "언급만": "◽",
    "혼조": "🟡",
}


def format_per_video(analysis: VideoAnalysis, *, vault_md_path_relative: str) -> str:
    v = analysis.video
    s = analysis.transcript_summary

    parts: list[str] = []
    parts.append(f"📺 {v.channel_name} — {v.title}")
    parts.append(f"🔗 {v.url}")
    parts.append(f"🕐 {v.published_at_utc.isoformat()}")
    parts.append("")
    parts.append("🎯 핵심 인사이트")
    for ins in s.key_insights:
        parts.append(f"• {ins}")
    parts.append("")
    parts.append("🚨 레드팀 시각")
    for rt in s.red_team:
        parts.append(f"• {rt}")
    parts.append("")

    label_suffix = (
        ", ".join(analysis.watchlist_hits)
        if analysis.watchlist_hits
        else f"자동 발견 {sum(1 for t in analysis.tickers if not t.in_watchlist)}개"
    )
    parts.append(f"📊 종목 영향 ({label_suffix})")
    for t in analysis.tickers:
        parts.append(_format_ticker_line(t))
    parts.append("")
    parts.append(f"📝 vault: {vault_md_path_relative}")
    return "\n".join(parts)


def format_daily_brief(brief: DailyBrief) -> str:
    parts: list[str] = []
    parts.append(f"📅 {brief.date.isoformat()} 일일 시장 브리핑")
    parts.append("")
    parts.append("🎯 오늘의 시장 read")
    parts.append(brief.market_read.strip())
    parts.append("")
    parts.append("🔑 핵심 인사이트")
    for ins in brief.key_insights:
        parts.append(f"• {ins}")
    parts.append("")
    parts.append("🚨 레드팀 시각")
    for rt in brief.red_team:
        parts.append(f"• {rt}")
    parts.append("")

    wl = [r for r in brief.ticker_rollup if r.in_watchlist]
    auto = [r for r in brief.ticker_rollup if not r.in_watchlist]

    if wl:
        parts.append("📊 워치리스트 종목별 영향")
        for r in wl:
            parts.append(_format_rollup_line(r))
        parts.append("")
    if auto:
        parts.append("🔍 자동 발견 종목")
        for r in auto:
            parts.append(_format_rollup_line(r))
        parts.append("")

    parts.append(f"📺 오늘 처리 영상 {len(brief.videos)}건")
    for v in brief.videos:
        parts.append(f"• {v.title} — {v.url}")

    return "\n".join(parts)


def _format_ticker_line(t: TickerMention) -> str:
    emoji = _DIRECTION_EMOJI.get(t.direction, "")
    label = t.display
    if t.symbol:
        label += f" ({t.symbol})"
    reason = _one_line(t.reasoning, 80)
    return f"• {label} {emoji} {t.direction} — {reason}"


def _format_rollup_line(r: TickerRollup) -> str:
    emoji = _DIRECTION_EMOJI.get(r.net_direction, "")
    label = r.display
    if r.symbol:
        label += f" ({r.symbol})"
    return f"• {label} {emoji} {r.net_direction} — {r.mention_count}개 영상 언급"


def _one_line(s: str, max_len: int) -> str:
    s = " ".join(s.split())
    return s if len(s) <= max_len else s[: max_len - 1] + "…"


def split_message(text: str, *, soft_cap: int = SOFT_CAP) -> list[str]:
    """Split a message into chunks ≤ soft_cap characters at sentence/newline boundaries.

    Adds `(i/n)` suffix to each chunk when more than one part. Preserves
    existing newline structure as much as possible.
    """
    if len(text) <= soft_cap:
        return [text]

    chunks: list[str] = []
    paragraphs = text.split("\n\n")
    buf = ""
    for p in paragraphs:
        candidate = (buf + "\n\n" + p) if buf else p
        if len(candidate) <= soft_cap:
            buf = candidate
            continue
        # current buf is full enough; flush
        if buf:
            chunks.append(buf)
            buf = ""
        # paragraph itself may exceed cap → split by lines
        if len(p) <= soft_cap:
            buf = p
        else:
            chunks.extend(_split_long_paragraph(p, soft_cap))
            buf = ""
    if buf:
        chunks.append(buf)

    n = len(chunks)
    if n <= 1:
        return chunks
    # Append (i/n). Re-check soft cap after suffix.
    tagged: list[str] = []
    for i, c in enumerate(chunks, 1):
        suffix = f"\n\n({i}/{n})"
        if len(c) + len(suffix) <= soft_cap + 32:
            tagged.append(c + suffix)
        else:
            # last-resort hard cut
            tagged.append(c[: soft_cap - len(suffix)] + suffix)
    return tagged


def _split_long_paragraph(p: str, soft_cap: int) -> list[str]:
    out: list[str] = []
    buf = ""
    for line in p.split("\n"):
        candidate = (buf + "\n" + line) if buf else line
        if len(candidate) <= soft_cap:
            buf = candidate
        else:
            if buf:
                out.append(buf)
            if len(line) <= soft_cap:
                buf = line
            else:
                # extreme: hard chunk a single line
                while len(line) > soft_cap:
                    out.append(line[:soft_cap])
                    line = line[soft_cap:]
                buf = line
    if buf:
        out.append(buf)
    return out


def format_messages(
    *, per_video: VideoAnalysis | None = None, daily: DailyBrief | None = None,
    vault_md_path_relative: str | None = None,
) -> Iterable[str]:
    """Convenience: format and split for a single send target."""
    if per_video is not None:
        if vault_md_path_relative is None:
            raise ValueError("vault_md_path_relative required for per_video format")
        yield from split_message(format_per_video(per_video, vault_md_path_relative=vault_md_path_relative))
    elif daily is not None:
        yield from split_message(format_daily_brief(daily))
    else:
        raise ValueError("either per_video or daily must be provided")
