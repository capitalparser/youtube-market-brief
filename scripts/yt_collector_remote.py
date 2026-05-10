#!/usr/bin/env python3
"""Standalone YouTube RSS collector for Korean financial channels.

Fetches RSS for configured channels, downloads transcripts, and saves
new videos as Markdown files under data/[channel_slug]/YYYY-MM-DD_title.md.

Outputs one __RESULT_JSON__ line on stdout with newly saved file paths.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import UTC, datetime, timezone
from pathlib import Path
from typing import Any

try:
    from youtube_transcript_api import YouTubeTranscriptApi
    from youtube_transcript_api._errors import (
        NoTranscriptFound,
        TranscriptsDisabled,
        VideoUnavailable,
    )
    TRANSCRIPT_AVAILABLE = True
except Exception:
    TRANSCRIPT_AVAILABLE = False

# ---------------------------------------------------------------------------
# Channel configuration — 3 Korean financial YouTube channels
# ---------------------------------------------------------------------------
CHANNELS: list[dict[str, str]] = [
    {"handle": "@hkglobalmarket", "slug": "hkglobalmarket", "name_ko": "HK글로벌마켓"},
    {"handle": "@MK_Invest",      "slug": "mk_invest",      "name_ko": "MK인베스트"},
    {"handle": "@kpunch",         "slug": "kpunch",         "name_ko": "한국경제"},
]

PREFERRED_LANGS = ("ko", "ko-KR", "en", "en-US", "ja", "zh-Hans", "zh-Hant")
MAX_TRANSCRIPT_CHARS = int(os.environ.get("TRANSCRIPT_MAX_CHARS", "80000"))
REPO_ROOT = Path(__file__).parent.parent
DATA_DIR = REPO_ROOT / "data"
KST = timezone(datetime.now(UTC).astimezone().utcoffset() or __import__("datetime").timedelta(hours=9))

try:
    import zoneinfo
    KST = zoneinfo.ZoneInfo("Asia/Seoul")
except Exception:
    from datetime import timedelta
    KST = timezone(timedelta(hours=9))


# ---------------------------------------------------------------------------
# RSS helpers
# ---------------------------------------------------------------------------
YT_FEED_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
YT_CHANNEL_PAGE = "https://www.youtube.com/{handle}"

_NS = {"atom": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}


def _http_get(url: str, timeout: int = 15) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def resolve_channel_id(handle: str) -> str | None:
    """Scrape YouTube channel page to get UCxxx channel_id."""
    for attempt_url in [
        f"https://www.youtube.com/{handle}",
        f"https://www.youtube.com/c/{handle.lstrip('@')}",
    ]:
        try:
            html = _http_get(attempt_url).decode("utf-8", errors="replace")
            m = re.search(r'"channelId"\s*:\s*"(UC[\w-]{22})"', html)
            if not m:
                m = re.search(r'"externalId"\s*:\s*"(UC[\w-]{22})"', html)
            if m:
                return m.group(1)
        except Exception:
            continue
    return None


def fetch_rss(channel_id: str) -> list[dict[str, Any]]:
    """Fetch YouTube RSS feed and return list of video dicts."""
    url = YT_FEED_URL.format(channel_id=channel_id)
    raw = _http_get(url)
    root = ET.fromstring(raw)

    videos = []
    for entry in root.findall("atom:entry", _NS):
        video_id_el = entry.find("yt:videoId", _NS)
        title_el = entry.find("atom:title", _NS)
        published_el = entry.find("atom:published", _NS)
        link_el = entry.find("atom:link", _NS)
        channel_name_el = entry.find("atom:author/atom:name", _NS)

        if video_id_el is None or title_el is None:
            continue

        video_id = video_id_el.text or ""
        title = title_el.text or ""
        published_raw = (published_el.text or "") if published_el is not None else ""
        url = (link_el.get("href", "") if link_el is not None else f"https://youtu.be/{video_id}")
        channel_name = (channel_name_el.text or "") if channel_name_el is not None else ""

        try:
            pub_dt = datetime.fromisoformat(published_raw.replace("Z", "+00:00"))
        except Exception:
            pub_dt = datetime.now(UTC)

        videos.append({
            "video_id": video_id,
            "title": title,
            "url": url,
            "published_at": pub_dt,
            "channel_name": channel_name,
        })

    return videos


# ---------------------------------------------------------------------------
# Transcript helpers
# ---------------------------------------------------------------------------

def fetch_transcript(video_id: str) -> tuple[str, str, bool]:
    """Returns (full_text, language, is_auto_generated). Empty string on failure."""
    if not TRANSCRIPT_AVAILABLE:
        return "", "unknown", False
    try:
        tlist = YouTubeTranscriptApi.list_transcripts(video_id)
        transcript = None
        for lang in PREFERRED_LANGS:
            try:
                transcript = tlist.find_transcript([lang])
                break
            except NoTranscriptFound:
                continue
        if transcript is None:
            for t in tlist:
                transcript = t
                break
        if transcript is None:
            return "", "unknown", False

        fetched = transcript.fetch()
        raw = fetched.to_raw_data() if hasattr(fetched, "to_raw_data") else fetched
        texts = []
        for seg in raw:
            if isinstance(seg, dict):
                texts.append(seg.get("text", ""))
            else:
                texts.append(getattr(seg, "text", ""))
        full_text = re.sub(r"\s+", " ", " ".join(texts)).strip()
        lang_code = getattr(
            fetched, "language_code",
            getattr(transcript, "language_code", getattr(transcript, "language", "unknown"))
        )
        is_auto = bool(getattr(fetched, "is_generated", getattr(transcript, "is_generated", False)))
        if len(full_text) > MAX_TRANSCRIPT_CHARS:
            full_text = full_text[:MAX_TRANSCRIPT_CHARS]
        return full_text, lang_code, is_auto
    except (TranscriptsDisabled, NoTranscriptFound, VideoUnavailable):
        return "", "unavailable", False
    except Exception as exc:
        print(f"[warn] transcript error for {video_id}: {exc}", file=sys.stderr)
        return "", "error", False


# ---------------------------------------------------------------------------
# Slug + filename helpers
# ---------------------------------------------------------------------------
_DISALLOWED = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WHITESPACE = re.compile(r"\s+")


def _slugify(s: str, max_len: int = 60) -> str:
    s = _DISALLOWED.sub("", s)
    s = _WHITESPACE.sub("_", s.strip())
    s = re.sub(r"-{2,}", "-", s)
    s = s.strip("-_.")
    return s[:max_len].rstrip("-_") if s else "video"


def _video_filename(published_at: datetime, title: str, video_id: str) -> str:
    kst_dt = published_at.astimezone(KST)
    date_str = kst_dt.strftime("%Y-%m-%d")
    title_slug = _slugify(title)
    suffix = video_id[-6:] if len(video_id) >= 6 else video_id
    return f"{date_str}_{title_slug}-{suffix}.md"


# ---------------------------------------------------------------------------
# Markdown writer
# ---------------------------------------------------------------------------

def _build_markdown(
    *,
    video_id: str,
    title: str,
    url: str,
    channel_name: str,
    channel_slug: str,
    published_at: datetime,
    transcript_text: str,
    transcript_language: str,
    is_auto_generated: bool,
) -> str:
    kst_dt = published_at.astimezone(KST)
    captured_at = datetime.now(KST).isoformat()
    date_str = kst_dt.strftime("%Y-%m-%d")
    safe_title = title.replace('"', "'")
    auto_str = str(is_auto_generated).lower()

    frontmatter = f"""---
source_url: {url}
source_type: youtube
captured_at: {captured_at}
tier: light
tags: []
video_id: {video_id}
channel: {channel_name}
channel_slug: {channel_slug}
date: {date_str}
title: "{safe_title}"
transcript_language: {transcript_language}
transcript_auto: {auto_str}
telegram_sent: false
---
"""
    script_section = f"\n## 스크립트\n\n{transcript_text}\n" if transcript_text else "\n## 스크립트\n\n(자막 없음)\n"
    return frontmatter + script_section


# ---------------------------------------------------------------------------
# Idempotency — track processed video IDs via existing data/ files
# ---------------------------------------------------------------------------

def _existing_video_ids(data_dir: Path) -> set[str]:
    ids: set[str] = set()
    if not data_dir.exists():
        return ids
    for md_file in data_dir.rglob("*.md"):
        try:
            text = md_file.read_text(encoding="utf-8")
            m = re.search(r"^video_id:\s*(\S+)", text, re.MULTILINE)
            if m:
                ids.add(m.group(1).strip())
        except Exception:
            pass
    return ids


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    today_kst = datetime.now(KST).date()
    cutoff = datetime(today_kst.year, today_kst.month, today_kst.day, tzinfo=KST)
    from datetime import timedelta
    cutoff = cutoff - timedelta(days=3)

    existing_ids = _existing_video_ids(DATA_DIR)
    saved_files: list[str] = []
    errors: list[str] = []

    for ch in CHANNELS:
        handle = ch["handle"]
        slug = ch["slug"]
        name_ko = ch["name_ko"]

        print(f"[info] Processing channel {handle} ({name_ko})", file=sys.stderr)

        channel_id = ch.get("channel_id")
        if not channel_id:
            print(f"[info]  Resolving channel ID for {handle}...", file=sys.stderr)
            try:
                channel_id = resolve_channel_id(handle)
            except Exception as e:
                print(f"[warn]  Failed to resolve {handle}: {e}", file=sys.stderr)
                errors.append(f"resolve:{handle}:{e}")
                continue
            if not channel_id:
                print(f"[warn]  Could not resolve channel ID for {handle}", file=sys.stderr)
                errors.append(f"resolve:{handle}:not_found")
                continue
            print(f"[info]  Resolved {handle} → {channel_id}", file=sys.stderr)

        try:
            videos = fetch_rss(channel_id)
        except Exception as e:
            print(f"[warn]  RSS fetch failed for {handle}: {e}", file=sys.stderr)
            errors.append(f"rss:{handle}:{e}")
            continue

        new_videos = [
            v for v in videos
            if v["video_id"] not in existing_ids and v["published_at"] >= cutoff
        ]
        print(f"[info]  {len(videos)} in RSS, {len(new_videos)} new", file=sys.stderr)

        channel_dir = DATA_DIR / slug
        channel_dir.mkdir(parents=True, exist_ok=True)

        for video in new_videos:
            vid_id = video["video_id"]
            title = video["title"]
            url = video["url"]
            pub = video["published_at"]

            print(f"[info]  Fetching transcript for {vid_id}: {title[:50]}", file=sys.stderr)
            transcript_text, lang, is_auto = fetch_transcript(vid_id)
            time.sleep(0.5)

            md_content = _build_markdown(
                video_id=vid_id,
                title=title,
                url=url,
                channel_name=video["channel_name"] or name_ko,
                channel_slug=slug,
                published_at=pub,
                transcript_text=transcript_text,
                transcript_language=lang,
                is_auto_generated=is_auto,
            )
            filename = _video_filename(pub, title, vid_id)
            filepath = channel_dir / filename
            filepath.write_text(md_content, encoding="utf-8")
            existing_ids.add(vid_id)
            saved_files.append(str(filepath.relative_to(REPO_ROOT)))
            print(f"[info]  Saved: {filepath.relative_to(REPO_ROOT)}", file=sys.stderr)

    result = {
        "date": today_kst.isoformat(),
        "files": saved_files,
        "new_count": len(saved_files),
        "errors": errors,
    }
    print(f"__RESULT_JSON__ {json.dumps(result, ensure_ascii=False)}")


if __name__ == "__main__":
    main()
