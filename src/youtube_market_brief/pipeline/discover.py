"""Channel resolution + new-video discovery filtered by IdempotencyStore."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from datetime import datetime

from youtube_market_brief._clients.youtube_data import YouTubeDataClient
from youtube_market_brief.domain.slugify import channel_slug
from youtube_market_brief.domain.types import ChannelConfig, VideoMeta
from youtube_market_brief.state.store import IdempotencyStore

log = logging.getLogger(__name__)


def discover_new_videos(
    *,
    channels: Iterable[ChannelConfig],
    yt: YouTubeDataClient,
    store: IdempotencyStore,
    published_after: datetime,
    skip_shorts: bool = True,
    max_results_per_channel: int = 25,
    on_resolved_channel: Callable[[str, str], None] | None = None,
) -> list[VideoMeta]:
    """For each enabled channel, list recent videos newer than `published_after`,
    drop those already in the IdempotencyStore, and return the union.

    `on_resolved_channel(channel_slug, resolved_channel_id)` is called when a
    handle is resolved to a channel_id — caller may persist this to channels.yaml
    to avoid future resolution quota cost (E6).
    """
    out: list[VideoMeta] = []
    for ch in channels:
        if not ch.enabled:
            continue
        cid = ch.channel_id
        if not cid:
            if not ch.handle:
                log.warning("channel '%s' has no channel_id and no handle — skipping", ch.name_ko)
                continue
            cid = yt.resolve_channel_id(ch.handle)
            if not cid:
                log.warning("could not resolve handle '%s' for channel '%s'", ch.handle, ch.name_ko)
                continue
            log.info("resolved handle '%s' → %s", ch.handle, cid)
            if on_resolved_channel:
                on_resolved_channel(ch.slug, cid)
        try:
            videos = yt.list_recent_videos(
                cid, published_after=published_after, max_results=max_results_per_channel
            )
        except Exception as e:
            log.error("discover failed for channel %s: %s", ch.name_ko, e)
            continue
        for v in videos:
            if store.has_video(v.video_id):
                continue
            if skip_shorts and v.duration_sec is not None and v.duration_sec < 90:
                log.info("skipping short %s (%ss)", v.video_id, v.duration_sec)
                continue
            stamped = VideoMeta(
                video_id=v.video_id,
                channel_id=v.channel_id,
                channel_name=v.channel_name,
                channel_slug=channel_slug(v.channel_name, hint=ch.slug),
                title=v.title,
                published_at_utc=v.published_at_utc,
                url=v.url,
                duration_sec=v.duration_sec,
            )
            out.append(stamped)
    out.sort(key=lambda v: v.published_at_utc)
    return out
