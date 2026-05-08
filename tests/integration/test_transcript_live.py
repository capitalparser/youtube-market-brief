from __future__ import annotations

import pytest

from youtube_market_brief._clients.transcript import YouTubeTranscriptApiClient
from youtube_market_brief.domain.types import Transcript, TranscriptSkip

pytestmark = pytest.mark.live


def test_fetch_returns_transcript_for_known_public_video() -> None:
    result = YouTubeTranscriptApiClient().fetch("UF8uR6Z6KLc")
    if isinstance(result, TranscriptSkip):
        pytest.skip(f"known public video transcript unavailable: {result.reason}")

    assert isinstance(result, Transcript)
    assert result.video_id == "UF8uR6Z6KLc"
    assert result.full_text
    assert result.segments


def test_fetch_returns_skip_for_invalid_id() -> None:
    result = YouTubeTranscriptApiClient().fetch("invalid_video_id_xxxxxx")

    assert isinstance(result, TranscriptSkip)
    assert result.video_id == "invalid_video_id_xxxxxx"
