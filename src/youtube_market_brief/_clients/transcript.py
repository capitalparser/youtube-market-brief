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

    Optional `cookie_file` (Netscape-format cookies.txt): loads browser
    cookies into a requests.Session and passes it as `http_client`. This
    authenticates requests as a real user, bypassing cloud-IP blocks without
    needing a proxy.

    Optional `proxy_config`: route through a residential proxy instead.
    Both can coexist; cookie_file takes precedence for the session.
    """

    def __init__(self, proxy_config=None, cookie_file: str | None = None):
        self._proxy_config = proxy_config
        self._cookie_file = cookie_file

    def _make_http_client(self):
        """Return an authenticated requests.Session if cookie_file is set."""
        if not self._cookie_file:
            return None
        cookie_path = Path(self._cookie_file)
        if not cookie_path.exists() or cookie_path.stat().st_size == 0:
            return None
        import http.cookiejar
        jar = http.cookiejar.MozillaCookieJar(str(cookie_path))
        try:
            jar.load(ignore_discard=True, ignore_expires=True)
        except Exception as exc:
            log.warning("failed to load cookie file %s: %s", cookie_path, exc)
            return None
        session = requests.Session()
        session.cookies = jar  # type: ignore[assignment]
        return session

    def fetch(self, video_id: str) -> Transcript | TranscriptSkip:
        try:
            http_client = self._make_http_client()
            transcript_list = _list_transcripts(video_id, self._proxy_config, http_client)
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


def _list_transcripts(video_id: str, proxy_config=None, http_client=None):
    if hasattr(YouTubeTranscriptApi, "list_transcripts"):
        # v0.6.x class method — no proxy/http_client support
        return YouTubeTranscriptApi.list_transcripts(video_id)
    # v1.x instance method — supports proxy_config + http_client
    kwargs: dict = {"proxy_config": proxy_config}
    if http_client is not None:
        kwargs["http_client"] = http_client
    api = YouTubeTranscriptApi(**kwargs)
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
        import yt_dlp  # lazy import — only needed when this client is active

        with tempfile.TemporaryDirectory() as tmpdir:
            self._run_ydl(yt_dlp, video_id, tmpdir)

            # Accept json3, vtt, srv3, ttml — whatever yt-dlp wrote
            sub_files = sorted(
                f for f in Path(tmpdir).iterdir()
                if f.suffix in (".json3", ".vtt", ".srv3", ".ttml")
            )
            if not sub_files:
                return TranscriptSkip(
                    video_id=video_id, reason="no_captions",
                    detail="yt-dlp: no subtitle files written",
                )

            # Prefer language in priority order
            chosen, chosen_lang = None, ""
            for lang in _YTDLP_LANG_PREF:
                matches = [f for f in sub_files if f".{lang}." in f.name]
                if matches:
                    chosen, chosen_lang = matches[0], lang
                    break
            if chosen is None:
                chosen = sub_files[0]
                parts = chosen.stem.split(".")
                chosen_lang = parts[-1] if len(parts) >= 2 else ""

            text = chosen.read_text(encoding="utf-8")
            ext = chosen.suffix.lstrip(".")

        segments = _ytdlp_parse_subtitle(text, ext)
        full_text = re.sub(r"\s+", " ", " ".join(s.text for s in segments)).strip()
        if not full_text:
            return TranscriptSkip(
                video_id=video_id, reason="no_captions",
                detail=f"yt-dlp subtitle empty (format={ext})",
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
        """Extract subtitle URLs via yt-dlp (auth only), then download with requests.

        Uses default web client (not android) so that browser cookies authenticate
        the session. extract_info(download=False) only fetches metadata — no video
        stream download, so PO token is not required at this step.
        """
        ydl_opts: dict = {
            "quiet": True,
            "no_warnings": True,
        }
        cookie_path = Path(self._cookie_file) if self._cookie_file else None
        using_cookies = False
        if cookie_path and cookie_path.exists() and cookie_path.stat().st_size > 0:
            ydl_opts["cookiefile"] = str(cookie_path)
            using_cookies = True
        log.info("yt-dlp extract_info video_id=%s cookiefile=%s", video_id, ydl_opts.get("cookiefile", "none"))

        url = _YT_WATCH.format(video_id=video_id)
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        if not info:
            return

        auto_subs: dict = info.get("automatic_captions") or {}
        manual_subs: dict = info.get("subtitles") or {}

        pref_ext = ("vtt", "json3", "srv3", "ttml")
        for lang in [*_YTDLP_LANG_PREF, "all"]:
            for subs in (manual_subs, auto_subs):
                if lang not in subs:
                    continue
                for fmt in (subs[lang] or []):
                    if fmt.get("ext") not in pref_ext:
                        continue
                    sub_url = fmt.get("url")
                    if not sub_url:
                        continue
                    resp = requests.get(sub_url, timeout=30)
                    resp.raise_for_status()
                    dest = Path(tmpdir) / f"{video_id}.{lang}.{fmt['ext']}"
                    dest.write_text(resp.text, encoding="utf-8")
                    return  # one subtitle file is enough


def _ytdlp_parse_subtitle(content: str, ext: str) -> tuple[Segment, ...]:
    """Dispatch to format-specific parser."""
    if ext == "json3":
        import json as _j
        return _ytdlp_parse_json3(_j.loads(content).get("events", []))
    # vtt / srv3 / ttml / anything else → strip to plain text lines
    return _ytdlp_parse_vtt(content)


def _ytdlp_parse_json3(events: list) -> tuple[Segment, ...]:
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
        segments.append(Segment(start=start_ms / 1000.0, duration=dur_ms / 1000.0, text=text))
    return tuple(segments)


_VTT_TIMESTAMP = re.compile(r"\d{2}:\d{2}:\d{2}\.\d{3} --> ")
_HTML_TAG = re.compile(r"<[^>]+>")


def _ytdlp_parse_vtt(content: str) -> tuple[Segment, ...]:
    """Parse WebVTT / srv3 / plain subtitle formats into Segments (no timing)."""
    segments = []
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("WEBVTT") or _VTT_TIMESTAMP.match(line):
            continue
        text = _HTML_TAG.sub("", line).strip()
        if text:
            segments.append(Segment(start=0.0, duration=0.0, text=text))
    return tuple(segments)
