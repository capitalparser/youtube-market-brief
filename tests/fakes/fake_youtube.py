from __future__ import annotations

from datetime import datetime

from youtube_market_brief.domain.types import VideoMeta


class FakeYouTubeClient:
    def __init__(
        self,
        *,
        handle_to_id: dict[str, str] | None = None,
        videos_by_channel: dict[str, list[VideoMeta]] | None = None,
    ):
        self._handle_to_id = handle_to_id or {}
        self._videos = videos_by_channel or {}
        self.resolve_calls: list[str] = []
        self.list_calls: list[tuple[str, datetime, int]] = []

    def resolve_channel_id(self, handle: str) -> str | None:
        self.resolve_calls.append(handle)
        return self._handle_to_id.get(handle)

    def list_recent_videos(
        self, channel_id: str, *, published_after: datetime, max_results: int = 25
    ) -> list[VideoMeta]:
        self.list_calls.append((channel_id, published_after, max_results))
        all_videos = self._videos.get(channel_id, [])
        return [v for v in all_videos if v.published_at_utc >= published_after][:max_results]
