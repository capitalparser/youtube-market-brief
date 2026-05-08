from datetime import UTC, datetime
from pathlib import Path

from tests.fakes.fake_youtube import FakeYouTubeClient
from youtube_market_brief.domain.types import ChannelConfig, VideoMeta
from youtube_market_brief.pipeline.discover import discover_new_videos
from youtube_market_brief.state.store import IdempotencyStore


def _v(
    vid: str,
    channel_id: str,
    title: str = "t",
    duration: int = 600,
    published_at: datetime | None = None,
) -> VideoMeta:
    return VideoMeta(
        video_id=vid,
        channel_id=channel_id,
        channel_name="ch",
        channel_slug="ch",
        title=title,
        published_at_utc=published_at or datetime(2026, 5, 7, 0, 0, tzinfo=UTC),
        url=f"https://youtu.be/{vid}",
        duration_sec=duration,
    )


def test_discover_filters_by_idempotency_store(tmp_path: Path):
    store = IdempotencyStore(tmp_path / "state.json")
    store.mark_video(
        "v1",
        channel_id="UCabc",
        outcome="ok",
        md_path=None,
        processed_at=datetime(2026, 5, 7, 0, 0, tzinfo=UTC),
    )
    yt = FakeYouTubeClient(videos_by_channel={"UCabc": [_v("v1", "UCabc"), _v("v2", "UCabc")]})
    channels = [ChannelConfig(channel_id="UCabc", name_ko="ch", slug="ch", enabled=True)]
    res = discover_new_videos(
        channels=channels,
        yt=yt,
        store=store,
        published_after=datetime(2026, 5, 1, tzinfo=UTC),
    )
    assert {v.video_id for v in res} == {"v2"}


def test_discover_skips_shorts(tmp_path: Path):
    store = IdempotencyStore(tmp_path / "state.json")
    yt = FakeYouTubeClient(videos_by_channel={"UCabc": [_v("v1", "UCabc", duration=30)]})
    channels = [ChannelConfig(channel_id="UCabc", name_ko="ch", slug="ch", enabled=True)]
    res = discover_new_videos(
        channels=channels,
        yt=yt,
        store=store,
        published_after=datetime(2026, 5, 1, tzinfo=UTC),
        skip_shorts=True,
    )
    assert res == []


def test_discover_resolves_handle(tmp_path: Path):
    store = IdempotencyStore(tmp_path / "state.json")
    yt = FakeYouTubeClient(
        handle_to_id={"@new_channel": "UCresolved"},
        videos_by_channel={"UCresolved": [_v("v1", "UCresolved")]},
    )
    resolved: list[tuple[str, str]] = []
    channels = [
        ChannelConfig(handle="@new_channel", name_ko="신규", slug="new_channel", enabled=True)
    ]
    res = discover_new_videos(
        channels=channels,
        yt=yt,
        store=store,
        published_after=datetime(2026, 5, 1, tzinfo=UTC),
        on_resolved_channel=lambda slug, cid: resolved.append((slug, cid)),
    )
    assert {v.video_id for v in res} == {"v1"}
    assert resolved == [("new_channel", "UCresolved")]
    assert yt.resolve_calls == ["@new_channel"]


def test_discover_disabled_channel_skipped(tmp_path: Path):
    store = IdempotencyStore(tmp_path / "state.json")
    yt = FakeYouTubeClient(videos_by_channel={"UCabc": [_v("v1", "UCabc")]})
    channels = [ChannelConfig(channel_id="UCabc", name_ko="ch", slug="ch", enabled=False)]
    res = discover_new_videos(
        channels=channels,
        yt=yt,
        store=store,
        published_after=datetime(2026, 5, 1, tzinfo=UTC),
    )
    assert res == []
    assert yt.list_calls == []


def test_discover_filters_exclusive_upper_bound(tmp_path: Path):
    store = IdempotencyStore(tmp_path / "state.json")
    yt = FakeYouTubeClient(
        videos_by_channel={
            "UCabc": [
                _v("in", "UCabc", published_at=datetime(2026, 5, 5, 15, 0, tzinfo=UTC)),
                _v("out", "UCabc", published_at=datetime(2026, 5, 6, 15, 0, tzinfo=UTC)),
            ]
        }
    )
    channels = [ChannelConfig(channel_id="UCabc", name_ko="ch", slug="ch", enabled=True)]
    res = discover_new_videos(
        channels=channels,
        yt=yt,
        store=store,
        published_after=datetime(2026, 5, 5, 0, 0, tzinfo=UTC),
        published_before=datetime(2026, 5, 6, 0, 0, tzinfo=UTC),
    )
    assert [v.video_id for v in res] == ["in"]


def test_discover_dedupes_same_video_across_channels(tmp_path: Path):
    store = IdempotencyStore(tmp_path / "state.json")
    same = _v("same", "UCabc")
    yt = FakeYouTubeClient(
        videos_by_channel={
            "UCabc": [same],
            "UCdef": [_v("same", "UCdef")],
        }
    )
    channels = [
        ChannelConfig(channel_id="UCabc", name_ko="a", slug="a", enabled=True),
        ChannelConfig(channel_id="UCdef", name_ko="b", slug="b", enabled=True),
    ]
    res = discover_new_videos(
        channels=channels,
        yt=yt,
        store=store,
        published_after=datetime(2026, 5, 1, tzinfo=UTC),
    )
    assert [v.video_id for v in res] == ["same"]
