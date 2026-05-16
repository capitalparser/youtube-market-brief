import json
from datetime import UTC, date, datetime
from pathlib import Path

from youtube_market_brief.domain.types import (
    DailyBrief,
    KeyInsight,
    LLMMeta,
    RedTeamItem,
    TickerMention,
    TranscriptSummary,
    VideoAnalysis,
    VideoMeta,
)
from youtube_market_brief.pipeline.aggregate import write_daily_brief_md
from youtube_market_brief.pipeline.write_video import write_video_md


def _make_analysis() -> VideoAnalysis:
    v = VideoMeta(
        video_id="abc123",
        channel_id="cid",
        channel_name="HK",
        channel_slug="hk",
        title="t",
        published_at_utc=datetime(2026, 5, 11, tzinfo=UTC),
        url="https://youtu.be/abc123",
    )
    s = TranscriptSummary(
        headline_3line=("a", "b", "c"),
        key_insights=(
            KeyInsight(
                text="i",
                sector_tags=("semiconductors",),
                theme_tags=(),
                why_important="중요",
                structural_shift="구조",
                pattern_connection="패턴",
                counter_signal="반례",
                workflow_implication="업무",
                signal_density="high",
            ),
        ),
        red_team=(RedTeamItem(text="r", sector_tags=(), theme_tags=()),),
        chars_used=0,
        was_truncated=False,
    )
    return VideoAnalysis(
        video=v,
        transcript_summary=s,
        tickers=(),
        watchlist_hits=(),
        tier="light",
        tags=("youtube",),
        llm_meta=LLMMeta(model="t", duration_ms=0),
        generated_at=datetime(2026, 5, 11, tzinfo=UTC),
    )


def test_write_video_md_creates_analysis_json_sidecar(tmp_path):
    a = _make_analysis()
    md_path = write_video_md(
        a,
        vault_youtube_root=tmp_path,
        captured_at=datetime(2026, 5, 11, tzinfo=UTC),
        date_kst_iso="2026-05-11",
    )
    sidecar = md_path.with_suffix(".analysis.json")
    assert sidecar.exists()
    data = json.loads(sidecar.read_text(encoding="utf-8"))
    assert data["video"]["video_id"] == "abc123"
    assert data["key_insights"][0]["text"] == "i"
    assert data["key_insights"][0]["sector_tags"] == ["semiconductors"]
    assert data["key_insights"][0]["why_important"] == "중요"
    assert data["key_insights"][0]["structural_shift"] == "구조"
    assert data["key_insights"][0]["pattern_connection"] == "패턴"
    assert data["key_insights"][0]["counter_signal"] == "반례"
    assert data["key_insights"][0]["workflow_implication"] == "업무"
    assert data["key_insights"][0]["signal_density"] == "high"


def test_write_daily_brief_md_creates_analysis_json_sidecar(tmp_path):
    brief = DailyBrief(
        date=date(2026, 5, 11),
        market_read="m",
        key_insights=(
            KeyInsight(text="ki", sector_tags=("financials",), theme_tags=(), why_important="중요"),
        ),
        red_team=(
            RedTeamItem(
                text="rt",
                sector_tags=(),
                theme_tags=("us_fiscal_debt",),
                counter_signal="반례",
                signal_density="medium",
            ),
        ),
        ticker_rollup=(),
        videos=(),
        llm_meta=LLMMeta(model="t", duration_ms=0),
    )
    md_path = write_daily_brief_md(
        brief,
        vault_daily_root=tmp_path,
        captured_at=datetime(2026, 5, 11, tzinfo=UTC),
    )
    sidecar = md_path.with_suffix(".analysis.json")
    assert sidecar.exists()
    data = json.loads(sidecar.read_text(encoding="utf-8"))
    assert data["date"] == "2026-05-11"
    assert data["key_insights"][0]["sector_tags"] == ["financials"]
    assert data["key_insights"][0]["why_important"] == "중요"
    assert data["red_team"][0]["theme_tags"] == ["us_fiscal_debt"]
    assert data["red_team"][0]["counter_signal"] == "반례"
    assert data["red_team"][0]["signal_density"] == "medium"
