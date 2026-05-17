"""Regression test: cmd_aggregate_only constructs DailyBrief with v1 typed objects.

Critical regression guard for the Task 7 schema migration:
cmd_aggregate_only was previously passing raw payload dicts/strings into
DailyBrief, causing AttributeError when render_daily_brief_markdown accessed
.text / .sector_tags on the elements.

This test exercises the post-LLM coerce-then-construct logic directly,
without needing CLI orchestration or a live vault.
"""

from __future__ import annotations

from youtube_market_brief.domain.types import DailyBrief, KeyInsight, RedTeamItem
from youtube_market_brief.pipeline.aggregate import _coerce_insight, _coerce_redteam


# ---------------------------------------------------------------------------
# Helpers that mirror the fixed cmd_aggregate_only logic
# ---------------------------------------------------------------------------

def _build_daily_brief_from_payload(payload: dict, target_date, video_metas, llm_meta):
    """Replicate the post-LLM DailyBrief construction in cmd_aggregate_only."""
    from youtube_market_brief.domain.types import TickerRollup

    market_read = (payload.get("market_read") or "").strip()
    key_insights = tuple(_coerce_insight(i) for i in (payload.get("key_insights") or []))
    red_team_raw = payload.get("red_team") or []
    if red_team_raw:
        red_team = tuple(_coerce_redteam(i) for i in red_team_raw)
    else:
        red_team = (
            RedTeamItem(
                text="(영상 간 합의가 약하거나 thesis가 분산되어 통합 반론 도출이 어려움)",
                sector_tags=(),
                theme_tags=(),
            ),
        )

    rollups: list[TickerRollup] = []
    for r in payload.get("ticker_rollup") or []:
        if not isinstance(r, dict):
            continue
        from youtube_market_brief.domain.types import TickerRollupVideoEntry
        per_video = tuple(
            TickerRollupVideoEntry(
                video_id=str(pv.get("video_id", "")),
                direction=pv.get("direction", "언급만"),
                one_line_reason=str(pv.get("one_line_reason", "")),
            )
            for pv in (r.get("per_video") or [])
            if isinstance(pv, dict)
        )
        rollups.append(
            TickerRollup(
                symbol=r.get("symbol"),
                display=str(r.get("display", "")),
                in_watchlist=bool(r.get("in_watchlist", False)),
                net_direction=r.get("net_direction", "혼조"),
                mention_count=int(r.get("mention_count", len(per_video))),
                per_video=per_video,
            )
        )

    return DailyBrief(
        date=target_date,
        market_read=market_read,
        key_insights=key_insights,
        red_team=red_team,
        ticker_rollup=tuple(rollups),
        videos=tuple(video_metas),
        llm_meta=llm_meta,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

V1_PAYLOAD = {
    "market_read": "AI 인프라 투자 확대 기조 지속",
    "key_insights": [
        {"text": "HBM 수요 견조", "sector_tags": ["semiconductors"], "theme_tags": ["memory_supercycle"]},
        {"text": "hyperscaler capex 상향", "sector_tags": ["software_ai_services"], "theme_tags": ["hyperscaler_capex"]},
        {"text": "원화 약세 수혜 예상", "sector_tags": [], "theme_tags": ["korea_discount"]},
    ],
    "red_team": [
        {"text": "capex ROI 불확실", "sector_tags": ["semiconductors"], "theme_tags": ["ai_meltup_bubble"]},
        {"text": "공급 과잉 우려", "sector_tags": ["semiconductors"], "theme_tags": ["memory_supercycle"]},
    ],
    "ticker_rollup": [
        {
            "symbol": "005930",
            "display": "삼성전자",
            "in_watchlist": True,
            "net_direction": "긍정적",
            "mention_count": 2,
            "per_video": [
                {"video_id": "abc123", "direction": "긍정적", "one_line_reason": "HBM3E 수주"},
            ],
        }
    ],
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_coerce_produces_key_insight_objects():
    """_coerce_insight turns v1 dicts into KeyInsight objects."""
    item = {"text": "HBM 수요 견조", "sector_tags": ["semiconductors"], "theme_tags": ["memory_supercycle"]}
    result = _coerce_insight(item)
    assert isinstance(result, KeyInsight)
    assert result.text == "HBM 수요 견조"
    assert result.sector_tags == ("semiconductors",)
    assert result.theme_tags == ("memory_supercycle",)


def test_coerce_produces_red_team_objects():
    """_coerce_redteam turns v1 dicts into RedTeamItem objects."""
    item = {"text": "capex ROI 불확실", "sector_tags": ["semiconductors"], "theme_tags": ["ai_meltup_bubble"]}
    result = _coerce_redteam(item)
    assert isinstance(result, RedTeamItem)
    assert result.text == "capex ROI 불확실"
    assert result.sector_tags == ("semiconductors",)


def test_daily_brief_constructed_with_typed_objects():
    """Core regression: DailyBrief.key_insights[0] is a KeyInsight, not a dict/str."""
    from datetime import date
    from youtube_market_brief.domain.types import LLMMeta

    llm_meta = LLMMeta(model="sonnet", duration_ms=500, was_retry=False)
    brief = _build_daily_brief_from_payload(
        payload=V1_PAYLOAD,
        target_date=date(2026, 5, 11),
        video_metas=(),
        llm_meta=llm_meta,
    )

    assert isinstance(brief, DailyBrief)

    # key_insights are KeyInsight objects (not dicts)
    assert len(brief.key_insights) == 3
    ki = brief.key_insights[0]
    assert isinstance(ki, KeyInsight)
    assert ki.text == "HBM 수요 견조"
    assert ki.sector_tags == ("semiconductors",)

    # red_team are RedTeamItem objects (not dicts)
    assert len(brief.red_team) == 2
    rt = brief.red_team[0]
    assert isinstance(rt, RedTeamItem)
    assert rt.text == "capex ROI 불확실"

    # .text access must not raise AttributeError (the original crash)
    _ = brief.key_insights[0].text
    _ = brief.red_team[0].text


def test_daily_brief_empty_red_team_uses_fallback():
    """When LLM returns empty red_team, fallback RedTeamItem is injected."""
    from datetime import date
    from youtube_market_brief.domain.types import LLMMeta

    payload_no_rt = {**V1_PAYLOAD, "red_team": []}
    llm_meta = LLMMeta(model="sonnet", duration_ms=100)
    brief = _build_daily_brief_from_payload(
        payload=payload_no_rt,
        target_date=date(2026, 5, 11),
        video_metas=(),
        llm_meta=llm_meta,
    )
    assert len(brief.red_team) == 1
    assert isinstance(brief.red_team[0], RedTeamItem)
    assert "합의가 약하거나" in brief.red_team[0].text


def test_coerce_handles_string_fallback():
    """_coerce_insight / _coerce_redteam handle legacy plain strings gracefully."""
    ki = _coerce_insight("plain string insight")
    assert isinstance(ki, KeyInsight)
    assert ki.text == "plain string insight"
    assert ki.sector_tags == ()

    rt = _coerce_redteam("plain string redteam")
    assert isinstance(rt, RedTeamItem)
    assert rt.text == "plain string redteam"
