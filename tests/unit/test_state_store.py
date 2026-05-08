from datetime import UTC, date, datetime
from pathlib import Path

from youtube_market_brief.state.store import IdempotencyStore


def test_create_and_persist(tmp_path: Path):
    p = tmp_path / "state.json"
    s = IdempotencyStore(p)
    assert not s.has_video("v1")
    s.mark_video(
        "v1",
        channel_id="UCabc",
        outcome="ok",
        md_path="00_Wiki/y/c/2026-05-07__t.md",
        processed_at=datetime(2026, 5, 7, 9, 0, tzinfo=UTC),
    )
    s.set_last_run(datetime(2026, 5, 7, 9, 1, tzinfo=UTC))
    s.flush()
    assert p.exists()

    s2 = IdempotencyStore(p)
    assert s2.has_video("v1")
    v = s2.get_video("v1")
    assert v is not None
    assert v.outcome == "ok"


def test_daily_brief_state(tmp_path: Path):
    p = tmp_path / "state.json"
    s = IdempotencyStore(p)
    d = date(2026, 5, 7)
    assert not s.daily_brief_sent(d)
    s.mark_daily_brief(d, brief_sent=True, brief_path="x.md")
    s.flush()

    s2 = IdempotencyStore(p)
    assert s2.daily_brief_sent(d) is True


def test_atomic_write_no_partial_on_error(tmp_path: Path, monkeypatch):
    """Force os.replace to fail mid-flush — original file should remain untouched."""

    p = tmp_path / "state.json"
    s = IdempotencyStore(p)
    s.mark_video(
        "v1",
        channel_id="UCabc",
        outcome="ok",
        md_path=None,
        processed_at=datetime(2026, 5, 7, 9, 0, tzinfo=UTC),
    )
    s.flush()

    original = p.read_bytes()

    # second flush will explode at os.replace
    def boom(src, dst):
        raise OSError("forced")

    monkeypatch.setattr("youtube_market_brief.state.store.os.replace", boom)
    s.mark_video(
        "v2",
        channel_id="UCabc",
        outcome="ok",
        md_path=None,
        processed_at=datetime(2026, 5, 7, 9, 1, tzinfo=UTC),
    )
    try:
        s.flush()
    except OSError:
        pass

    assert p.read_bytes() == original
