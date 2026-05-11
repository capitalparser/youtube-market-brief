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
