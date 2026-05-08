"""YouTube Data API v3 client (channel resolution + recent videos).

Public functions only need an API key. Caption download is NOT used here
(needs channel-owner OAuth which we don't have for external channels).
The transcript client uses youtube-transcript-api separately.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Protocol

from youtube_market_brief.domain.types import VideoMeta

_DUR_RE = re.compile(
    r"^PT"
    r"(?:(?P<hours>\d+)H)?"
    r"(?:(?P<minutes>\d+)M)?"
    r"(?:(?P<seconds>\d+)S)?"
    r"$"
)


class YouTubeDataClient(Protocol):
    def resolve_channel_id(self, handle: str) -> str | None:
        """Resolve an @handle to a channel_id (UCxxx). None if not found."""
        ...

    def list_recent_videos(
        self,
        channel_id: str,
        *,
        published_after: datetime,
        max_results: int = 25,
    ) -> list[VideoMeta]:
        """Return recent uploads (published_at >= published_after, KST aware).

        Skips livestreams in progress and Shorts (<90s) — caller may further filter.
        """
        ...


class GoogleAPIYouTubeDataClient:
    """Concrete impl using google-api-python-client.

    Implementation note (Codex):
    - Use `discovery.build("youtube", "v3", developerKey=...)`
    - For handle resolution: `youtube.search().list(q=handle, type="channel", part="id")`
      then take first item's `id.channelId`.
    - For recent videos:
      1. `youtube.channels().list(id=channel_id, part="contentDetails")` →
         get `uploads` playlist id from `contentDetails.relatedPlaylists.uploads`
      2. `youtube.playlistItems().list(playlistId=uploads, part="contentDetails,snippet", maxResults=...)`
      3. Filter by `published_at`. Then for each video:
         `youtube.videos().list(id=...,part="contentDetails,snippet,liveStreamingDetails")`
         to retrieve duration (ISO8601) and live status.
    - Skip if `liveBroadcastContent != "none"`.
    - Skip if `duration_sec < 90` and config.skip_shorts.
    - Map ISO 8601 duration to seconds with `isodate` or manual parser.
    """

    def __init__(self, api_key: str):
        self._api_key = api_key
        self._client = None  # built lazily by Codex impl

    def _youtube(self):
        if not self._api_key:
            raise ValueError("YOUTUBE_API_KEY required")
        if self._client is None:
            from googleapiclient.discovery import build

            self._client = build("youtube", "v3", developerKey=self._api_key)
        return self._client

    def resolve_channel_id(self, handle: str) -> str | None:
        youtube = self._youtube()
        response = (
            youtube.search()
            .list(q=handle, type="channel", part="id", maxResults=1)
            .execute()
        )
        items = response.get("items", [])
        if not items:
            return None
        return items[0].get("id", {}).get("channelId")

    def list_recent_videos(
        self,
        channel_id: str,
        *,
        published_after: datetime,
        max_results: int = 25,
    ) -> list[VideoMeta]:
        youtube = self._youtube()
        published_after = _as_utc(published_after)

        channel_response = (
            youtube.channels().list(id=channel_id, part="contentDetails").execute()
        )
        channel_items = channel_response.get("items", [])
        if not channel_items:
            return []

        uploads_id = (
            channel_items[0]
            .get("contentDetails", {})
            .get("relatedPlaylists", {})
            .get("uploads")
        )
        if not uploads_id:
            return []

        playlist_response = (
            youtube.playlistItems()
            .list(
                playlistId=uploads_id,
                part="contentDetails,snippet",
                maxResults=max_results,
            )
            .execute()
        )

        candidates: dict[str, datetime] = {}
        for item in playlist_response.get("items", []):
            snippet = item.get("snippet", {})
            published_at_raw = snippet.get("publishedAt")
            video_id = item.get("contentDetails", {}).get("videoId")
            if not published_at_raw or not video_id:
                continue
            published_at = parse_iso8601_published(published_at_raw)
            if published_at >= published_after:
                candidates[video_id] = published_at

        if not candidates:
            return []

        videos_response = (
            youtube.videos()
            .list(
                id=",".join(candidates),
                part="contentDetails,snippet,liveStreamingDetails",
            )
            .execute()
        )

        videos: list[VideoMeta] = []
        for item in videos_response.get("items", []):
            snippet = item.get("snippet", {})
            if snippet.get("liveBroadcastContent") != "none":
                continue

            video_id = item.get("id")
            if not video_id:
                continue

            published_at_raw = snippet.get("publishedAt")
            fallback_published_at = candidates.get(video_id)
            if not published_at_raw and fallback_published_at is None:
                continue
            published_at = (
                parse_iso8601_published(published_at_raw)
                if published_at_raw
                else fallback_published_at
            )
            videos.append(
                VideoMeta(
                    video_id=video_id,
                    channel_id=channel_id,
                    channel_name=snippet.get("channelTitle", ""),
                    channel_slug="",
                    title=snippet.get("title", ""),
                    published_at_utc=published_at,
                    url=f"https://youtu.be/{video_id}",
                    duration_sec=_parse_iso_duration_sec(
                        item.get("contentDetails", {}).get("duration", "")
                    ),
                )
            )

        return sorted(videos, key=lambda v: v.published_at_utc)


def parse_iso8601_published(s: str) -> datetime:
    """Parse YouTube ISO8601 timestamps (`2026-05-07T00:14:32Z`) as UTC tz-aware."""
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _parse_iso_duration_sec(s: str) -> int | None:
    match = _DUR_RE.match(s)
    if not match:
        return None
    hours = int(match.group("hours") or 0)
    minutes = int(match.group("minutes") or 0)
    seconds = int(match.group("seconds") or 0)
    return hours * 3600 + minutes * 60 + seconds
