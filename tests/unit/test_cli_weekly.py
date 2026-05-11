import json
from datetime import UTC, date, datetime


def test_load_weekly_briefs_reads_present_days(tmp_path):
    from youtube_market_brief.pipeline.weekly import load_weekly_briefs

    daily_root = tmp_path / "00_Wiki" / "youtube" / "_daily"
    daily_root.mkdir(parents=True)
    for d in (date(2026, 5, 5), date(2026, 5, 6), date(2026, 5, 9)):
        sidecar = daily_root / f"{d.isoformat()}_brief.analysis.json"
        sidecar.write_text(json.dumps({
            "date": d.isoformat(),
            "captured_at": "2026-05-12T00:00:00",
            "market_read": "m",
            "key_insights": [
                {"text": "i", "sector_tags": ["semiconductors"], "theme_tags": []}
            ],
            "red_team": [],
            "ticker_rollup": [],
            "videos": [],
            "llm_meta": {"model": "t", "duration_ms": 0, "claude_session_id": None},
        }, ensure_ascii=False), encoding="utf-8")

    briefs = load_weekly_briefs(vault_daily_root=daily_root, week_start=date(2026, 5, 5))
    assert len(briefs) == 3
    assert {b.date for b in briefs} == {date(2026, 5, 5), date(2026, 5, 6), date(2026, 5, 9)}


def test_load_weekly_briefs_empty_dir_returns_empty(tmp_path):
    from youtube_market_brief.pipeline.weekly import load_weekly_briefs
    daily_root = tmp_path / "00_Wiki" / "youtube" / "_daily"
    daily_root.mkdir(parents=True)
    briefs = load_weekly_briefs(vault_daily_root=daily_root, week_start=date(2026, 5, 5))
    assert briefs == []


def test_load_weekly_briefs_nonexistent_dir_returns_empty(tmp_path):
    from youtube_market_brief.pipeline.weekly import load_weekly_briefs
    daily_root = tmp_path / "nope"
    briefs = load_weekly_briefs(vault_daily_root=daily_root, week_start=date(2026, 5, 5))
    assert briefs == []


def test_aggregate_weekly_zero_briefs_returns_none(tmp_path):
    from youtube_market_brief.pipeline.weekly import aggregate_weekly
    daily_root = tmp_path / "_daily"
    daily_root.mkdir()
    result = aggregate_weekly(week_start=date(2026, 5, 5), vault_daily_root=daily_root)
    assert result is None


def test_aggregate_weekly_with_briefs_returns_rollup(tmp_path):
    from youtube_market_brief.pipeline.weekly import aggregate_weekly

    daily_root = tmp_path / "_daily"
    daily_root.mkdir()
    sidecar = daily_root / "2026-05-05_brief.analysis.json"
    sidecar.write_text(json.dumps({
        "date": "2026-05-05",
        "captured_at": "2026-05-12T00:00:00",
        "market_read": "m",
        "key_insights": [{"text": "i", "sector_tags": ["semiconductors"], "theme_tags": []}],
        "red_team": [],
        "ticker_rollup": [],
        "videos": [],
        "llm_meta": {"model": "t", "duration_ms": 0, "claude_session_id": None},
    }, ensure_ascii=False), encoding="utf-8")

    result = aggregate_weekly(week_start=date(2026, 5, 5), vault_daily_root=daily_root)
    assert result is not None
    assert result.week_start == date(2026, 5, 5)
    assert len(result.daily_briefs_present) == 1


def test_write_weekly_md_creates_md_and_sidecar(tmp_path):
    from youtube_market_brief.pipeline.weekly import write_weekly_md
    from youtube_market_brief.domain.types import WeeklyRollup

    rollup = WeeklyRollup(
        week_start=date(2026, 5, 5), week_end=date(2026, 5, 11),
        daily_briefs_present=(), daily_briefs_missing=(),
        tickers=(), sectors=(), themes=(), total_videos=0,
    )
    out = write_weekly_md(
        rollup,
        vault_weekly_root=tmp_path,
        captured_at=datetime(2026, 5, 12, tzinfo=UTC),
    )
    assert out.exists()
    sidecar = out.with_suffix(".analysis.json")
    assert sidecar.exists()
    data = json.loads(sidecar.read_text(encoding="utf-8"))
    assert data["week_start"] == "2026-05-05"
    assert data["total_videos"] == 0


def test_last_monday():
    from youtube_market_brief.pipeline.weekly import last_monday
    # 2026-05-11 is a Monday (weekday=0)
    assert last_monday(date(2026, 5, 11)) == date(2026, 5, 11)
    # 2026-05-12 is Tuesday → last Monday is 5-11
    assert last_monday(date(2026, 5, 12)) == date(2026, 5, 11)
    # 2026-05-17 is Sunday → last Monday is 5-11
    assert last_monday(date(2026, 5, 17)) == date(2026, 5, 11)


def test_cmd_weekly_brief_skips_telegram_when_credentials_missing(tmp_path, monkeypatch, capsys):
    """cmd_weekly_brief must not attempt HTTP send when bot_token/chat_id are empty."""
    import json
    from datetime import date
    from types import SimpleNamespace
    from youtube_market_brief.cli import cmd_weekly_brief
    from youtube_market_brief.config import AppConfig
    from pathlib import Path

    # Set up vault with 1 sidecar so aggregate_weekly returns a rollup
    vault = tmp_path / "vault"
    daily_root = vault / "00_Wiki" / "youtube" / "_daily"
    weekly_root = vault / "00_Wiki" / "youtube" / "_weekly"
    daily_root.mkdir(parents=True)
    sidecar = daily_root / "2026-05-05_brief.analysis.json"
    sidecar.write_text(json.dumps({
        "date": "2026-05-05", "captured_at": "2026-05-12T00:00:00",
        "market_read": "m",
        "key_insights": [{"text": "i", "sector_tags": [], "theme_tags": []}],
        "red_team": [], "ticker_rollup": [], "videos": [],
        "llm_meta": {"model": "t", "duration_ms": 0, "claude_session_id": None},
    }, ensure_ascii=False), encoding="utf-8")

    cfg = AppConfig(
        project_root=tmp_path / "proj",
        vault_root=vault,
        youtube_api_key="", telegram_bot_token="", telegram_chat_id="",
        llm_provider="api", openai_api_key="", openai_model="",
        claude_bin="", claude_model="", claude_timeout_sec=300,
        webshare_proxy_username="", webshare_proxy_password="",
        transcript_backend="", youtube_cookie_file="",
        dry_run=False, log_level="INFO", transcript_max_chars=80000,
        max_videos_per_run=20, skip_shorts=True, timezone="Asia/Seoul",
        channels_path=Path("/dev/null"),
        watchlist_path=Path("/dev/null"),
        prompts_dir=Path("/dev/null"),
    )

    args = SimpleNamespace(week_start="2026-05-05", dry_run=False, no_telegram=False)
    rc = cmd_weekly_brief(args, cfg)
    assert rc == 0
    captured = capsys.readouterr()
    assert "Telegram skipped" in captured.out


def test_load_weekly_briefs_preserves_video_meta_round_trip(tmp_path):
    """Sidecar should round-trip VideoMeta fields (channel_id, channel_name, published_at_utc)."""
    import json
    from datetime import date
    from youtube_market_brief.pipeline.weekly import load_weekly_briefs

    daily_root = tmp_path / "_daily"
    daily_root.mkdir()
    sidecar = daily_root / "2026-05-05_brief.analysis.json"
    sidecar.write_text(json.dumps({
        "date": "2026-05-05", "captured_at": "2026-05-12T00:00:00",
        "market_read": "m",
        "key_insights": [{"text": "i", "sector_tags": [], "theme_tags": []}],
        "red_team": [],
        "ticker_rollup": [],
        "videos": [
            {
                "video_id": "abc", "channel_id": "UC123", "channel_name": "HK Global",
                "channel_slug": "hk", "title": "테스트", "url": "https://youtu.be/abc",
                "published_at_utc": "2026-05-05T12:00:00+00:00",
            }
        ],
        "llm_meta": {"model": "t", "duration_ms": 0, "claude_session_id": None},
    }, ensure_ascii=False), encoding="utf-8")

    briefs = load_weekly_briefs(vault_daily_root=daily_root, week_start=date(2026, 5, 5))
    assert len(briefs) == 1
    v = briefs[0].videos[0]
    assert v.channel_id == "UC123"
    assert v.channel_name == "HK Global"
    assert v.published_at_utc.year == 2026
    assert v.published_at_utc.month == 5
