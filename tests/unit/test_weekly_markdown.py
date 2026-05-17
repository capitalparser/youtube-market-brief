from datetime import UTC, date, datetime
from pathlib import Path

import yaml

from youtube_market_brief.config import AppConfig
from youtube_market_brief.domain.daily_brief import render_weekly_brief_markdown
from youtube_market_brief.domain.types import (
    WeeklyRollup,
    WeeklySectorEntry,
    WeeklyThemeEntry,
    WeeklyTickerDayEntry,
    WeeklyTickerEntry,
)


def _make_rollup() -> WeeklyRollup:
    return WeeklyRollup(
        week_start=date(2026, 5, 5),
        week_end=date(2026, 5, 11),
        daily_briefs_present=(date(2026, 5, 5), date(2026, 5, 6)),
        daily_briefs_missing=(date(2026, 5, 7),),
        tickers=(
            WeeklyTickerEntry(
                symbol="005930", display="삼성전자", in_watchlist=True,
                sector_tag=None,
                days_mentioned=2, total_mentions=3,
                directions=("긍정적", "부정적"),
                net_weekly_direction="혼조",
                per_day=(
                    WeeklyTickerDayEntry(date(2026, 5, 5), "긍정적", 1),
                    WeeklyTickerDayEntry(date(2026, 5, 6), "부정적", 2),
                ),
            ),
        ),
        sectors=(
            WeeklySectorEntry(
                sector_slug="semiconductors", insight_days=2,
                total_insight_mentions=3, related_tickers=("005930",),
            ),
        ),
        themes=(
            WeeklyThemeEntry(
                theme_slug="hyperscaler_capex", insight_days=1,
                total_insight_mentions=1, related_tickers=(),
            ),
        ),
        total_videos=5,
    )


def test_weekly_md_frontmatter_has_required_fields():
    md = render_weekly_brief_markdown(_make_rollup(), captured_at=datetime(2026, 5, 12, tzinfo=UTC))
    assert md.startswith("---\n")
    end = md.index("\n---\n", 4)
    fm = yaml.safe_load(md[4:end])
    # date string is fine — yaml.safe_load returns string or date; either is OK
    assert fm["week_start"] in (date(2026, 5, 5), "2026-05-05")
    assert fm["week_end"] in (date(2026, 5, 11), "2026-05-11")
    assert fm["total_videos"] == 5
    assert fm["source_type"] == "youtube_weekly_brief"
    assert "weekly_brief" in fm["tags"]


def test_weekly_md_body_includes_ticker_table():
    md = render_weekly_brief_markdown(_make_rollup(), captured_at=datetime(2026, 5, 12, tzinfo=UTC))
    assert "삼성전자" in md
    assert "005930" in md
    assert "혼조" in md
    # Either "2/7" format or "2일" present (depends on implementation choice)
    assert "2/7" in md or "2일" in md


def test_weekly_md_body_includes_sector_heatmap():
    md = render_weekly_brief_markdown(_make_rollup(), captured_at=datetime(2026, 5, 12, tzinfo=UTC))
    assert "semiconductors" in md


def test_weekly_md_body_includes_theme_heatmap():
    md = render_weekly_brief_markdown(_make_rollup(), captured_at=datetime(2026, 5, 12, tzinfo=UTC))
    assert "hyperscaler_capex" in md


def test_weekly_md_notes_missing_briefs():
    md = render_weekly_brief_markdown(_make_rollup(), captured_at=datetime(2026, 5, 12, tzinfo=UTC))
    assert "2026-05-07" in md


def test_app_config_has_vault_weekly_root():
    cfg = AppConfig(
        project_root=Path("/tmp"),
        vault_root=Path("/tmp/vault"),
        youtube_api_key="", telegram_bot_token="", telegram_chat_id="",
        llm_provider="api", openai_api_key="", openai_model="",
        claude_bin="", claude_model="", claude_timeout_sec=300,
        webshare_proxy_username="", webshare_proxy_password="",
        youtube_proxy_url="",
        transcript_backend="", youtube_cookie_file="",
        enable_stt_fallback=False, stt_model="gpt-4o-mini-transcribe", stt_audio_max_mb=24,
        dry_run=False, log_level="INFO", transcript_max_chars=80000,
        max_videos_per_run=20, skip_shorts=True, timezone="Asia/Seoul",
        channels_path=Path("/tmp/c.yaml"),
        watchlist_path=Path("/tmp/w.yaml"),
        prompts_dir=Path("/tmp/prompts"),
    )
    assert cfg.vault_weekly_root == Path("/tmp/vault/00_Wiki/youtube/_weekly")
