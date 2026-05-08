from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest

from youtube_market_brief._clients.youtube_data import GoogleAPIYouTubeDataClient

pytestmark = pytest.mark.live


@pytest.fixture
def youtube_client() -> GoogleAPIYouTubeDataClient:
    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        pytest.skip("YOUTUBE_API_KEY not set")
    return GoogleAPIYouTubeDataClient(api_key)


def test_resolve_known_handle(youtube_client: GoogleAPIYouTubeDataClient) -> None:
    channel_id = youtube_client.resolve_channel_id("@hkglobalmarket")

    assert channel_id is not None
    assert channel_id.startswith("UC")


def test_list_recent_videos_returns_list(youtube_client: GoogleAPIYouTubeDataClient) -> None:
    channel_id = youtube_client.resolve_channel_id("@hkglobalmarket")
    assert channel_id is not None

    videos = youtube_client.list_recent_videos(
        channel_id,
        published_after=datetime(2020, 1, 1, tzinfo=UTC),
        max_results=5,
    )

    assert isinstance(videos, list)
    if videos:
        first = videos[0]
        assert first.video_id
        assert first.url == f"https://youtu.be/{first.video_id}"
        assert first.published_at_utc.tzinfo is not None
