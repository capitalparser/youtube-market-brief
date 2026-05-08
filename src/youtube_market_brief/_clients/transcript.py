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
        NoTranscriptFound,
        TranscriptsDisabled,
        VideoUnavailable,
    )
except ImportError:  # pragma: no cover - legacy import path
    from youtube_transcript_api import _errors

    NoTranscriptFound = _errors.NoTranscriptFound
    TranscriptsDisabled = _errors.TranscriptsDisabled
    VideoUnavailable = _errors.VideoUnavailable

_PREFERRED_LANGS = ("ko", "ko-KR", "en", "en-US", "ja", "zh-Hans", "zh-Hant")


class TranscriptClient(Protocol):
    def fetch(self, video_id: str) -> Transcript | TranscriptSkip:
        ...


class YouTubeTranscriptApiClient:
    """Concrete impl using `youtube_transcript_api`.

    Implementation note (Codex):
    - `from youtube_transcript_api import YouTubeTranscriptApi, _errors`
    - Try `YouTubeTranscriptApi.list_transcripts(video_id)` → iterate languages
      in priority order from `_PREFERRED_LANGS`.
    - For each candidate, call `.fetch()` and build `Segment` tuples.
    - Catch `TranscriptsDisabled` → SkipReason="disabled"
    - Catch `NoTranscriptFound` → SkipReason="no_captions"
    - Catch any other internal-shape error → SkipReason="api_changed"
      (this signals that the library / YouTube internals diverged — flag it!)
    - Catch `requests` Timeout → SkipReason="timeout"
    """

    def fetch(self, video_id: str) -> Transcript | TranscriptSkip:
        try:
            transcript_list = _list_transcripts(video_id)
            transcript = _find_preferred_transcript(transcript_list)
            if transcript is None:
                return TranscriptSkip(
                    video_id=video_id,
                    reason="no_captions",
                    detail="No transcript found for preferred or fallback languages",
                )
            return _build_transcript(video_id, transcript)
        except TranscriptsDisabled as exc:
            return TranscriptSkip(video_id=video_id, reason="disabled", detail=str(exc))
        except NoTranscriptFound as exc:
            return TranscriptSkip(video_id=video_id, reason="no_captions", detail=str(exc))
        except VideoUnavailable as exc:
            return TranscriptSkip(video_id=video_id, reason="geo_blocked", detail=str(exc))
        except (TimeoutError, requests.Timeout) as exc:
            return TranscriptSkip(video_id=video_id, reason="timeout", detail=str(exc))
        except Exception as exc:
            return TranscriptSkip(video_id=video_id, reason="api_changed", detail=str(exc))


def _now_utc() -> datetime:
    return datetime.now(tz=UTC)


def _list_transcripts(video_id: str):
    if hasattr(YouTubeTranscriptApi, "list_transcripts"):
        return YouTubeTranscriptApi.list_transcripts(video_id)
    return YouTubeTranscriptApi().list(video_id)


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
