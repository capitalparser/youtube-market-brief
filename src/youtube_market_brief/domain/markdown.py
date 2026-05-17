"""Per-video markdown serialization with PAS Wiki-compatible frontmatter."""

from __future__ import annotations

from datetime import datetime
from io import StringIO

import yaml

from youtube_market_brief.domain.types import (
    TickerMention,
    VideoAnalysis,
)

_DIRECTION_EMOJI = {
    "긍정적": "🟢",
    "중립": "⚪",
    "부정적": "🔴",
    "언급만": "◽",
}


def render_video_markdown(analysis: VideoAnalysis, *, captured_at: datetime) -> str:
    """Render a complete per-video markdown document (frontmatter + body)."""
    fm = _frontmatter(analysis, captured_at=captured_at)
    body = _body(analysis)
    return f"---\n{fm}---\n\n{body}"


def _frontmatter(analysis: VideoAnalysis, *, captured_at: datetime) -> str:
    s = analysis.transcript_summary
    ki_sectors = sorted({tag for ki in s.key_insights for tag in ki.sector_tags})
    ki_themes = sorted({tag for ki in s.key_insights for tag in ki.theme_tags})
    rt_sectors = sorted({tag for rt in s.red_team for tag in rt.sector_tags})
    rt_themes = sorted({tag for rt in s.red_team for tag in rt.theme_tags})

    data = {
        "captured_at": captured_at.isoformat(),
        "channel": analysis.video.channel_slug,
        "insight_sector_tags": ki_sectors,
        "insight_theme_tags": ki_themes,
        "red_team_sector_tags": rt_sectors,
        "red_team_theme_tags": rt_themes,
        "source_type": "youtube",
        "source_url": analysis.video.url,
        "tags": list(analysis.tags),
        "tier": analysis.tier,
        "video_id": analysis.video.video_id,
        "was_truncated": s.was_truncated,
        "watchlist_hits": list(analysis.watchlist_hits),
    }
    buf = StringIO()
    yaml.safe_dump(data, buf, allow_unicode=True, sort_keys=True)
    return buf.getvalue()


def _body(analysis: VideoAnalysis) -> str:
    v = analysis.video
    s = analysis.transcript_summary
    parts: list[str] = []
    parts.append(f"# {v.title}\n")
    parts.append(
        f"> {v.channel_name} · {v.published_at_utc.isoformat()} · [원본]({v.url})\n"
    )
    if s.was_truncated:
        parts.append(
            "> ⚠️ 자막이 컨텍스트 한도를 초과해 일부 발췌만 분석에 사용됨.\n"
        )

    parts.append("## 3줄 헤드라인\n")
    for line in s.headline_3line:
        parts.append(f"- {line}")
    parts.append("")

    parts.append("## 🎯 핵심 인사이트\n")
    for ins in s.key_insights:
        parts.append(f"- {ins.text}")
    parts.append("")

    parts.append("## 🚨 레드팀 시각 (반대 관점·리스크·의문점)\n")
    for rt in s.red_team:
        parts.append(f"- {rt.text}")
    parts.append("")

    parts.append("## 📊 종목 영향\n")
    in_wl = [t for t in analysis.tickers if t.in_watchlist]
    auto = [t for t in analysis.tickers if not t.in_watchlist]
    if in_wl:
        parts.append("### 워치리스트 hit\n")
        for t in in_wl:
            parts.extend(_ticker_block(t))
    if auto:
        parts.append("### 자동 발견 종목\n")
        for t in auto:
            parts.extend(_ticker_block(t))
    if not in_wl and not auto:
        parts.append("_언급된 종목 없음._\n")

    return "\n".join(parts).rstrip() + "\n"


def _ticker_block(t: TickerMention) -> list[str]:
    emoji = _DIRECTION_EMOJI.get(t.direction, "")
    label = f"**{t.display}"
    if t.symbol:
        label += f" ({t.symbol})"
    label += f"** — {emoji} {t.direction} / 신뢰도 {t.confidence}"
    out = [f"- {label}"]
    if t.reasoning:
        out.append(f"  - 근거: {t.reasoning}")
    for q in t.quotes:
        out.append(f'  - 인용: "{q}"')
    return [*out, ""]
