"""LLM-driven per-video analysis (`claude` CLI subprocess).

Steps:
1. Compose user prompt = transcript + video meta + watchlist YAML serialization
2. Call LLM with system prompt loaded from prompts/system_video_analysis.ko.md
3. Extract fenced JSON block; validate against expected schema
4. Reconcile in_watchlist flags + canonical symbols against config
5. Apply watchlist filter rules (quotes required, exclude '언급만', etc.)
6. Determine capture depth (light/deep) and tags
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import yaml

from youtube_market_brief._clients.llm import LLMClient, extract_fenced_json
from youtube_market_brief.domain import watchlist as wl_domain
from youtube_market_brief.domain.types import (
    KeyInsight,
    LLMMeta,
    RedTeamItem,
    TickerMention,
    Transcript,
    TranscriptSummary,
    VideoAnalysis,
    VideoMeta,
    Watchlist,
)

log = logging.getLogger(__name__)


def analyze_video(
    *,
    video: VideoMeta,
    transcript: Transcript,
    watchlist: Watchlist,
    llm: LLMClient,
    system_prompt_path: Path,
    timeout_sec: int = 300,
    max_retries: int = 1,
) -> VideoAnalysis:
    system = system_prompt_path.read_text(encoding="utf-8")
    user = _compose_user_prompt(video=video, transcript=transcript, watchlist=watchlist)

    response_text: str
    duration_ms: int
    session_id: str | None
    was_retry = False
    last_err: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            resp = llm.call(system=system, user=user, timeout_sec=timeout_sec)
            response_text = resp.text
            duration_ms = resp.duration_ms
            session_id = resp.session_id
            payload = extract_fenced_json(response_text)
            parsed = _parse_video_payload(payload)
            break
        except Exception as e:
            last_err = e
            log.warning("analyze attempt %d failed for %s: %s", attempt + 1, video.video_id, e)
            if attempt < max_retries:
                was_retry = True
                user = user + (
                    "\n\n# 재시도 지시\n앞선 응답이 스키마를 위반했다. 반드시 JSON only, "
                    "fenced ```json ... ``` 블록만 출력. key_insights 3-5개, red_team 2-4개, "
                    "tickers 배열, watchlist_hits 배열을 모두 포함하라."
                )
            else:
                raise AnalyzeError(f"analyze failed for {video.video_id}: {last_err}") from last_err

    headline_3line = parsed["headline_3line"]

    key_insights: tuple[KeyInsight, ...] = tuple(
        KeyInsight(
            text=str(item["text"]).strip(),
            sector_tags=tuple(item.get("sector_tags") or []),
            theme_tags=tuple(item.get("theme_tags") or []),
        )
        for item in parsed["key_insights"]
    )
    red_team_raw = parsed["red_team"]
    if red_team_raw:
        red_team: tuple[RedTeamItem, ...] = tuple(
            RedTeamItem(
                text=str(item["text"]).strip(),
                sector_tags=tuple(item.get("sector_tags") or []),
                theme_tags=tuple(item.get("theme_tags") or []),
            )
            for item in red_team_raw
        )
    else:
        red_team = (
            RedTeamItem(
                text="(영상이 단편 사실 보도, 별도 반론 없음)",
                sector_tags=(),
                theme_tags=(),
            ),
        )

    raw_tickers = parsed["tickers"]

    # Reconcile against config
    mentions = tuple(_to_ticker_mention(t) for t in raw_tickers)
    mentions = wl_domain.annotate_in_watchlist(mentions, watchlist)
    hits = wl_domain.filter_watchlist_hits(mentions, watchlist)

    tier = "deep" if hits else "light"
    tags = _compute_tags(video=video, mentions=mentions, hits=hits)

    return VideoAnalysis(
        video=video,
        transcript_summary=TranscriptSummary(
            headline_3line=tuple(headline_3line[:3]) + ("",) * max(0, 3 - len(headline_3line)),
            key_insights=key_insights,
            red_team=red_team,
            chars_used=transcript.char_count,
            was_truncated=transcript.was_truncated,
        ),
        tickers=mentions,
        watchlist_hits=hits,
        tier=tier,
        tags=tags,
        llm_meta=LLMMeta(
            model="sonnet",
            duration_ms=duration_ms,
            was_retry=was_retry,
            claude_session_id=session_id,
        ),
        generated_at=datetime.now(tz=UTC),
    )


def _compose_user_prompt(*, video: VideoMeta, transcript: Transcript, watchlist: Watchlist) -> str:
    video_meta = {
        "video_id": video.video_id,
        "title": video.title,
        "channel_name": video.channel_name,
        "url": video.url,
        "published_at_utc": video.published_at_utc.isoformat(),
        "duration_sec": video.duration_sec,
    }
    wl_payload = {
        "tickers": [
            {
                "symbol": e.symbol,
                "market": e.market,
                "name_ko": e.name_ko,
                "name_en": e.name_en,
                "aliases": list(e.aliases),
            }
            for e in watchlist.entries
        ]
    }
    return (
        "## video_meta\n"
        + json.dumps(video_meta, ensure_ascii=False, indent=2)
        + "\n\n## watchlist (YAML)\n"
        + yaml.safe_dump(wl_payload, allow_unicode=True, sort_keys=False)
        + "\n## transcript\n"
        + ("(was_truncated=true)\n" if transcript.was_truncated else "")
        + transcript.full_text
    )


def _parse_video_payload(payload) -> dict:
    """v1 schema strict validation.

    key_insights / red_team: list of {text, sector_tags, theme_tags} objects.
    tickers: 각 항목에 sector_tag (str | null).
    sector_tags / theme_tags / sector_tag: SECTOR_SLUGS / THEME_SLUGS 엄격 검증
    (whitespace-padded 슬러그는 contract violation으로 거절).
    """
    from youtube_market_brief.domain.taxonomy import is_valid_sector, is_valid_theme

    if not isinstance(payload, dict):
        raise ValueError("expected JSON object at top level")
    for key in ("headline_3line", "key_insights", "red_team", "tickers", "watchlist_hits"):
        if key not in payload:
            raise ValueError(f"missing required field: {key}")

    if not isinstance(payload["headline_3line"], list) or len(payload["headline_3line"]) < 1:
        raise ValueError("headline_3line must be non-empty list")

    if not isinstance(payload["key_insights"], list) or not (3 <= len(payload["key_insights"]) <= 5):
        raise ValueError("key_insights must be 3-5 items")
    for i, item in enumerate(payload["key_insights"]):
        if not isinstance(item, dict) or "text" not in item:
            raise ValueError(f"key_insights[{i}] must be object with 'text'")
        if not isinstance(item.get("sector_tags", []), list):
            raise ValueError(f"key_insights[{i}].sector_tags must be list")
        for s in item.get("sector_tags") or []:
            if not is_valid_sector(s):
                raise ValueError(f"key_insights[{i}].sector_tags invalid slug: {s!r}")
        if not isinstance(item.get("theme_tags", []), list):
            raise ValueError(f"key_insights[{i}].theme_tags must be list")
        for t in item.get("theme_tags") or []:
            if not is_valid_theme(t):
                raise ValueError(f"key_insights[{i}].theme_tags invalid slug: {t!r}")

    if not isinstance(payload["red_team"], list):
        raise ValueError("red_team must be list")
    for i, item in enumerate(payload["red_team"]):
        if not isinstance(item, dict) or "text" not in item:
            raise ValueError(f"red_team[{i}] must be object with 'text'")
        if not isinstance(item.get("sector_tags", []), list):
            raise ValueError(f"red_team[{i}].sector_tags must be list")
        for s in item.get("sector_tags") or []:
            if not is_valid_sector(s):
                raise ValueError(f"red_team[{i}].sector_tags invalid slug: {s!r}")
        if not isinstance(item.get("theme_tags", []), list):
            raise ValueError(f"red_team[{i}].theme_tags must be list")
        for t in item.get("theme_tags") or []:
            if not is_valid_theme(t):
                raise ValueError(f"red_team[{i}].theme_tags invalid slug: {t!r}")

    if not isinstance(payload["tickers"], list):
        raise ValueError("tickers must be list")
    for i, t in enumerate(payload["tickers"]):
        sector_tag = t.get("sector_tag")
        if sector_tag is not None and not is_valid_sector(sector_tag):
            raise ValueError(f"tickers[{i}].sector_tag invalid: {sector_tag!r}")

    if not isinstance(payload["watchlist_hits"], list):
        raise ValueError("watchlist_hits must be list")
    return payload


_VALID_DIRECTIONS = {"긍정적", "중립", "부정적", "언급만"}
_VALID_CONFIDENCES = {"high", "medium", "low"}


def _to_ticker_mention(d: dict) -> TickerMention:
    direction = d.get("direction", "언급만")
    if direction not in _VALID_DIRECTIONS:
        direction = "언급만"
    confidence = d.get("confidence", "low")
    if confidence not in _VALID_CONFIDENCES:
        confidence = "low"
    quotes = d.get("quotes") or []
    if not isinstance(quotes, list):
        quotes = []
    sector_tag = d.get("sector_tag")
    if sector_tag == "":
        sector_tag = None
    return TickerMention(
        symbol=d.get("symbol") or None,
        display=d.get("display", "").strip() or "(unknown)",
        in_watchlist=bool(d.get("in_watchlist")),
        sector_tag=sector_tag,
        direction=direction,  # type: ignore[arg-type]
        reasoning=d.get("reasoning", "").strip(),
        quotes=tuple(q for q in quotes if isinstance(q, str)),
        confidence=confidence,  # type: ignore[arg-type]
    )


def _compute_tags(
    *, video: VideoMeta, mentions: tuple[TickerMention, ...], hits: tuple[str, ...]
) -> tuple[str, ...]:
    tags: list[str] = ["youtube", video.channel_slug]
    for s in hits:
        tags.append(s)
    # Add up to 3 auto-discovered ticker displays for searchability
    auto_displays = [t.display for t in mentions if not t.in_watchlist and t.display]
    for d in auto_displays[:3]:
        if d not in tags:
            tags.append(d)
    return tuple(tags)


class AnalyzeError(RuntimeError):
    pass
