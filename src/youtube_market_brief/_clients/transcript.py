"""Transcript clients: youtube-transcript-api (default) + yt-dlp (cloud fallback).

YouTubeTranscriptApiClient  — scrapes YouTube caption endpoint directly.
                              Fast, but blocked on cloud-provider IPs (GitHub Actions etc.).
YtDlpTranscriptClient       — uses yt-dlp Python API; different request path and
                              headers that can bypass IP blocks. Optionally accepts
                              a Netscape-format cookies file for authenticated requests.

Both implement TranscriptClient Protocol and return the same Transcript/TranscriptSkip types.
Select via TRANSCRIPT_BACKEND env: "youtube_transcript_api" (default) | "yt_dlp".
"""

from __future__ import annotations

import logging
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

import requests

from youtube_market_brief.domain.types import Segment, Transcript, TranscriptSkip

log = logging.getLogger(__name__)

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


# ---------------------------------------------------------------------------
# yt-dlp based client
# ---------------------------------------------------------------------------

_YT_WATCH = "https://www.youtube.com/watch?v={video_id}"
_YTDLP_LANG_PREF = ["ko", "ko-KR", "en", "en-US", "ja", "zh-Hans", "zh-Hant"]


class YtDlpTranscriptClient:
    """Transcript client backed by yt-dlp.

    Uses yt-dlp's internal downloader to fetch auto-generated or manual
    subtitles without downloading the video. Unlike youtube-transcript-api,
    yt-dlp uses different request patterns that can bypass cloud-IP blocks.

    Optional: pass `cookie_file` (path to a Netscape-format cookies.txt) to
    authenticate as a logged-in user — further reduces chance of being blocked.
    """

    def __init__(self, cookie_file: str | None = None):
        self._cookie_file = cookie_file

    def fetch(self, video_id: str) -> Transcript | TranscriptSkip:
        try:
            return self._fetch(video_id)
        except Exception as exc:
            return TranscriptSkip(
                video_id=video_id,
                reason="api_changed",
                detail=f"yt-dlp {type(exc).__name__}: {str(exc)[:300]}",
            )

    def _fetch(self, video_id: str) -> Transcript | TranscriptSkip:
        import json as _json

        import yt_dlp  # lazy import — only needed when this client is active

        with tempfile.TemporaryDirectory() as tmpdir:
            # download=True with skip_download=True → writes subtitle files, skips video
            self._run_ydl(yt_dlp, video_id, tmpdir)

            # Find written .json3 subtitle files
            json3_files = sorted(Path(tmpdir).glob(f"{video_id}.*.json3"))
            if not json3_files:
                return TranscriptSkip(
                    video_id=video_id, reason="no_captions",
                    detail="yt-dlp: no subtitle files written",
                )

            # Pick preferred language
            chosen, chosen_lang = None, ""
            for lang in _YTDLP_LANG_PREF:
                matches = [f for f in json3_files if f.name.endswith(f".{lang}.json3")]
                if matches:
                    chosen, chosen_lang = matches[0], lang
                    break
            if chosen is None:
                chosen = json3_files[0]
                parts = chosen.name.split(".")
                chosen_lang = parts[-2] if len(parts) >= 3 else ""

            events = _json.loads(chosen.read_text(encoding="utf-8")).get("events", [])

        segments = _ytdlp_parse_json3(events)
        full_text = re.sub(r"\s+", " ", " ".join(s.text for s in segments)).strip()
        if not full_text:
            return TranscriptSkip(
                video_id=video_id, reason="no_captions",
                detail="yt-dlp subtitle text is empty",
            )
        return Transcript(
            video_id=video_id,
            language=chosen_lang,
            is_auto_generated=True,
            segments=segments,
            full_text=full_text,
            char_count=len(full_text),
            fetched_at=_now_utc(),
        )

    def _run_ydl(self, yt_dlp, video_id: str, tmpdir: str) -> None:
        ydl_opts: dict = {
            "skip_download": True,
            "writeautomaticsub": True,
            "writesubtitles": True,
            "subtitleslangs": [*_YTDLP_LANG_PREF, "all"],
            "subtitlesformat": "json3",
            "outtmpl": f"{tmpdir}/%(id)s.%(ext)s",
            "quiet": True,
            "no_warnings": True,
        }
        cookie_path = Path(self._cookie_file) if self._cookie_file else None
        if cookie_path and cookie_path.exists() and cookie_path.stat().st_size > 0:
            ydl_opts["cookiefile"] = str(cookie_path)

        url = _YT_WATCH.format(video_id=video_id)
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])  # download=True → subtitle files written to tmpdir


def _ytdlp_parse_json3(events: list) -> tuple[Segment, ...]:
    """Convert yt-dlp JSON3 events to Segment tuples."""
    segments = []
    for event in events:
        start_ms = event.get("tStartMs", 0)
        dur_ms = event.get("dDurationMs", 0)
        segs = event.get("segs")
        if not segs:
            continue
        text = "".join(s.get("utf8", "") for s in segs).strip()
        if not text or text == "\n":
            continue
        segments.append(Segment(
            start=start_ms / 1000.0,
            duration=dur_ms / 1000.0,
            text=text,
        ))
    return tuple(segments)
