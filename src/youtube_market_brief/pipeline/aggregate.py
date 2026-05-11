"""Daily brief synthesis (LLM-driven) + markdown writing."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from datetime import date, datetime
from pathlib import Path

from youtube_market_brief._clients.llm import LLMClient, extract_fenced_json
from youtube_market_brief.domain.daily_brief import (
    compute_rollup,
    render_daily_brief_markdown,
)
from youtube_market_brief.domain.types import (
    DailyBrief,
    KeyInsight,
    LLMMeta,
    RedTeamItem,
    TickerRollup,
    TickerRollupVideoEntry,
    VideoAnalysis,
)

log = logging.getLogger(__name__)


def _coerce_insight(item) -> KeyInsight:
    """Accept v1 dict or transitional string, normalize to KeyInsight."""
    if isinstance(item, dict):
        return KeyInsight(
            text=str(item.get("text", "")).strip(),
            sector_tags=tuple(item.get("sector_tags") or []),
            theme_tags=tuple(item.get("theme_tags") or []),
        )
    return KeyInsight(text=str(item).strip(), sector_tags=(), theme_tags=())


def _coerce_redteam(item) -> RedTeamItem:
    """Accept v1 dict or transitional string, normalize to RedTeamItem."""
    if isinstance(item, dict):
        return RedTeamItem(
            text=str(item.get("text", "")).strip(),
            sector_tags=tuple(item.get("sector_tags") or []),
            theme_tags=tuple(item.get("theme_tags") or []),
        )
    return RedTeamItem(text=str(item).strip(), sector_tags=(), theme_tags=())


def aggregate_daily(
    *,
    analyses: Iterable[VideoAnalysis],
    target_date: date,
    llm: LLMClient,
    system_prompt_path: Path,
    timeout_sec: int = 300,
) -> DailyBrief | None:
    """Compose a DailyBrief from per-video analyses. Returns None if no analyses."""
    al = list(analyses)
    if not al:
        return None

    # Pre-compute deterministic rollup (math) — LLM may also produce it,
    # but we trust our own for quantities. The LLM provides market_read,
    # key_insights, red_team narrative.
    deterministic_rollup = compute_rollup(al)

    system = system_prompt_path.read_text(encoding="utf-8")
    user_payload = {
        "date": target_date.isoformat(),
        "analyses": [_serialize_analysis(a) for a in al],
    }
    user = "## input\n```json\n" + json.dumps(user_payload, ensure_ascii=False, indent=2) + "\n```"
    resp = llm.call(system=system, user=user, timeout_sec=timeout_sec)
    payload = extract_fenced_json(resp.text)
    if not isinstance(payload, dict):
        raise ValueError("daily brief payload not a dict")
    market_read = payload.get("market_read", "").strip()

    key_insights = tuple(_coerce_insight(i) for i in payload.get("key_insights", []))
    red_team_raw = payload.get("red_team", [])
    if red_team_raw:
        red_team = tuple(_coerce_redteam(i) for i in red_team_raw)
    else:
        red_team = (
            RedTeamItem(text="(영상 간 합의가 약하거나 thesis가 분산되어 통합 반론 도출이 어려움)", sector_tags=(), theme_tags=()),
        )

    # Use deterministic rollup, but enrich one_line_reason from LLM's per_video
    # answers if available (otherwise our reasoning summaries stand).
    enriched = _maybe_enrich_rollup(deterministic_rollup, payload.get("ticker_rollup", []))

    return DailyBrief(
        date=target_date,
        market_read=market_read,
        key_insights=key_insights,
        red_team=red_team,
        ticker_rollup=enriched,
        videos=tuple(a.video for a in al),
        llm_meta=LLMMeta(
            model="sonnet",
            duration_ms=resp.duration_ms,
            was_retry=False,
            claude_session_id=resp.session_id,
        ),
    )


def write_daily_brief_md(
    brief: DailyBrief,
    *,
    vault_daily_root: Path,
    captured_at: datetime,
) -> Path:
    """Write the daily brief MD + JSON sidecar. Returns the absolute path of the MD."""
    vault_daily_root.mkdir(parents=True, exist_ok=True)
    out = vault_daily_root / f"{brief.date.isoformat()}_brief.md"
    body = render_daily_brief_markdown(brief, captured_at=captured_at)
    out.write_text(body, encoding="utf-8")
    log.info("wrote daily brief MD: %s", out)

    sidecar = out.with_suffix(".analysis.json")
    sidecar_data = {
        "date": brief.date.isoformat(),
        "captured_at": captured_at.isoformat(),
        "market_read": brief.market_read,
        "key_insights": [
            {"text": ki.text, "sector_tags": list(ki.sector_tags), "theme_tags": list(ki.theme_tags)}
            for ki in brief.key_insights
        ],
        "red_team": [
            {"text": rt.text, "sector_tags": list(rt.sector_tags), "theme_tags": list(rt.theme_tags)}
            for rt in brief.red_team
        ],
        "ticker_rollup": [
            {
                "symbol": r.symbol,
                "display": r.display,
                "in_watchlist": r.in_watchlist,
                "net_direction": r.net_direction,
                "mention_count": r.mention_count,
                "per_video": [
                    {"video_id": e.video_id, "direction": e.direction, "one_line_reason": e.one_line_reason}
                    for e in r.per_video
                ],
            }
            for r in brief.ticker_rollup
        ],
        "videos": [
            {
                "video_id": v.video_id,
                "channel_id": v.channel_id,
                "channel_name": v.channel_name,
                "channel_slug": v.channel_slug,
                "title": v.title,
                "published_at_utc": v.published_at_utc.isoformat(),
                "url": v.url,
            }
            for v in brief.videos
        ],
        "llm_meta": {
            "model": brief.llm_meta.model,
            "duration_ms": brief.llm_meta.duration_ms,
            "claude_session_id": brief.llm_meta.claude_session_id,
        },
    }
    sidecar.write_text(
        json.dumps(sidecar_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log.info("wrote daily brief sidecar: %s", sidecar)

    return out


def _serialize_analysis(a: VideoAnalysis) -> dict:
    return {
        "video": {
            "video_id": a.video.video_id,
            "channel_name": a.video.channel_name,
            "title": a.video.title,
            "url": a.video.url,
        },
        "headline_3line": list(a.transcript_summary.headline_3line),
        "key_insights": [
            {"text": ki.text, "sector_tags": list(ki.sector_tags), "theme_tags": list(ki.theme_tags)}
            for ki in a.transcript_summary.key_insights
        ],
        "red_team": [
            {"text": rt.text, "sector_tags": list(rt.sector_tags), "theme_tags": list(rt.theme_tags)}
            for rt in a.transcript_summary.red_team
        ],
        "tickers": [
            {
                "symbol": t.symbol,
                "display": t.display,
                "in_watchlist": t.in_watchlist,
                "sector_tag": t.sector_tag,
                "direction": t.direction,
                "reasoning": t.reasoning,
                "quotes": list(t.quotes),
                "confidence": t.confidence,
            }
            for t in a.tickers
        ],
        "watchlist_hits": list(a.watchlist_hits),
    }


def _maybe_enrich_rollup(
    deterministic: tuple[TickerRollup, ...], llm_rollup: list
) -> tuple[TickerRollup, ...]:
    if not isinstance(llm_rollup, list):
        return deterministic
    by_key = {}
    for r in llm_rollup:
        if not isinstance(r, dict):
            continue
        key = (r.get("symbol") or r.get("display") or "").strip()
        if not key:
            continue
        by_key[key] = r
    enriched: list[TickerRollup] = []
    for det in deterministic:
        key = det.symbol or det.display
        llm = by_key.get(key)
        if llm and isinstance(llm.get("per_video"), list):
            llm_pv = {p.get("video_id"): p.get("one_line_reason", "") for p in llm["per_video"] if isinstance(p, dict)}
            new_pv = tuple(
                TickerRollupVideoEntry(
                    video_id=e.video_id,
                    direction=e.direction,
                    one_line_reason=llm_pv.get(e.video_id) or e.one_line_reason,
                )
                for e in det.per_video
            )
            enriched.append(
                TickerRollup(
                    symbol=det.symbol,
                    display=det.display,
                    in_watchlist=det.in_watchlist,
                    net_direction=det.net_direction,
                    mention_count=det.mention_count,
                    per_video=new_pv,
                )
            )
        else:
            enriched.append(det)
    return tuple(enriched)
