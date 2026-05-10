"""youtube-transcript-api wrapper with multi-language fallback.

Returns a Transcript for any available caption (preferring Korean, then
English, then any auto-generated). Returns TranscriptSkip when no captions
exist or the library cannot fetch them.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Protocol

import requests

from youtube_market_brief.domain.types import Segment, Transcript, TranscriptSkip

try:
    from youtube_transcript_api import YouTubeTranscriptApi
except ImportError:  # pragma: no cover - legacy import path
    from youtube_transcript_api._api import YouTubeTranscriptApi

try:
    from youtube_transcript_api._errors import (
        IpBlocked,
        NoTranscriptFound,
        RequestBlocked,
        TranscriptsDisabled,
        VideoUnavailable,
    )
except ImportError:  # pragma: no cover - legacy import path
    from youtube_transcript_api import _errors

    NoTranscriptFound = _errors.NoTranscriptFound
    TranscriptsDisabled = _errors.TranscriptsDisabled
    VideoUnavailable = _errors.VideoUnavailable
    RequestBlocked = getattr(_errors, "RequestBlocked", Exception)
    IpBlocked = getattr(_errors, "IpBlocked", Exception)

_PREFERRED_LANGS = ("ko", "ko-KR", "en", "en-US", "ja", "zh-Hans", "zh-Hant")


class TranscriptClient(Protocol):
    def fetch(self, video_id: str) -> Transcript | TranscriptSkip:
        ...


class YouTubeTranscriptApiClient:
    """Concrete impl using `youtube_transcript_api`.

    Pass `proxy_config` (a `youtube_transcript_api.proxies.ProxyConfig` instance,
    e.g. `WebshareProxyConfig`) to route requests through a residential proxy —
    required when running on cloud-provider IPs that YouTube blocks.
    """

    def __init__(self, proxy_config=None):
        self._proxy_config = proxy_config

    def fetch(self, video_id: str) -> Transcript | TranscriptSkip:
        try:
            transcript_list = _list_transcripts(video_id, self._proxy_config)
            transcript = _find_preferred_transcript(transcript_list)
            if transcript is None:
                return TranscriptSkip(
                    video_id=video_id,
                    reason="no_captions",
                    detail="No transcript found for preferred or fallback languages",
                )
            return _build_transcript(video_id, transcript)
        except (IpBlocked, RequestBlocked) as exc:
            return TranscriptSkip(video_id=video_id, reason="ip_blocked", detail=str(exc)[:300])
        except TranscriptsDisabled as exc:
            return TranscriptSkip(video_id=video_id, reason="disabled", detail=str(exc))
        except NoTranscriptFound as exc:
            return TranscriptSkip(video_id=video_id, reason="no_captions", detail=str(exc))
        except VideoUnavailable as exc:
            return TranscriptSkip(video_id=video_id, reason="geo_blocked", detail=str(exc))
        except (TimeoutError, requests.Timeout) as exc:
            return TranscriptSkip(video_id=video_id, reason="timeout", detail=str(exc))
        except Exception as exc:
            return TranscriptSkip(
                video_id=video_id,
                reason="api_changed",
                detail=f"{type(exc).__name__}: {str(exc)[:300]}",
            )


def _now_utc() -> datetime:
    return datetime.now(tz=UTC)


def _list_transcripts(video_id: str, proxy_config=None):
    if hasattr(YouTubeTranscriptApi, "list_transcripts"):
        # v0.6.x class method — no proxy support
        return YouTubeTranscriptApi.list_transcripts(video_id)
    # v1.x instance method — supports proxy_config
    api = YouTubeTranscriptApi(proxy_config=proxy_config)
    return api.list(video_id)


def _find_preferred_transcript(transcript_list):
    for lang in _PREFERRED_LANGS:
        try:
            return transcript_list.find_transcript([lang])
        except NoTranscriptFound:
            continue

    for transcript in transcript_list:
        return transcript
    return None


def _build_transcript(video_id: str, transcript) -> Transcript:
    fetched = transcript.fetch()
    raw_segments = fetched.to_raw_data() if hasattr(fetched, "to_raw_data") else fetched

    segments = tuple(
        Segment(
            start=float(_segment_value(segment, "start", 0.0)),
            duration=float(_segment_value(segment, "duration", 0.0)),
            text=str(_segment_value(segment, "text", "")),
        )
        for segment in raw_segments
    )
    full_text = re.sub(r"\s+", " ", " ".join(segment.text for segment in segments)).strip()
    language = getattr(
        fetched,
        "language_code",
        getattr(transcript, "language_code", getattr(transcript, "language", "")),
    )
    is_auto_generated = bool(
        getattr(fetched, "is_generated", getattr(transcript, "is_generated", False))
    )

    return Transcript(
        video_id=video_id,
        language=language,
        is_auto_generated=is_auto_generated,
        segments=segments,
        full_text=full_text,
        char_count=len(full_text),
        fetched_at=_now_utc(),
    )


def _segment_value(segment, name: str, default):
    if isinstance(segment, dict):
        return segment.get(name, default)
    return getattr(segment, name, default)
