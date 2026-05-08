"""Filesystem-safe slug generation for channel names and video titles.

Korean characters are preserved when safe (Obsidian/macOS handle them); only
disallowed characters are stripped or replaced. Falls back to a deterministic
hash suffix when collisions or empty results occur.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata

# Reserved on Windows + sensible elsewhere; spaces collapsed to underscore.
_DISALLOWED = re.compile(r"[<>:\"/\\|?*\x00-\x1f]")
_WHITESPACE = re.compile(r"\s+")
_MULTI_DASH = re.compile(r"-{2,}")


def channel_slug(name: str, *, hint: str | None = None) -> str:
    """Compute a deterministic, filesystem-safe slug for a channel.

    `hint` (e.g. user-provided slug in channels.yaml) is preferred when given.
    """
    if hint:
        slug = _normalize(hint)
        if slug:
            return slug
    slug = _normalize(name)
    if not slug:
        slug = _hash8(name)
    return slug


def video_slug(title: str, video_id: str, *, max_len: int = 60) -> str:
    """Compute a slug for a video title, falling back to video_id.

    Always suffixes with last 6 chars of video_id to ensure uniqueness across
    re-uploads of similarly-titled videos.
    """
    base = _normalize(title)
    if not base:
        base = "video"
    if len(base) > max_len:
        base = base[:max_len].rstrip("-_")
    suffix = video_id[-6:] if len(video_id) >= 6 else video_id
    return f"{base}-{suffix}"


def _normalize(s: str) -> str:
    s = unicodedata.normalize("NFC", s)
    s = _DISALLOWED.sub("", s)
    s = _WHITESPACE.sub("_", s.strip())
    s = _MULTI_DASH.sub("-", s)
    s = s.strip("-_.")
    return s


def _hash8(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:8]
