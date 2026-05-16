from datetime import UTC, datetime

from youtube_market_brief._clients.transcript import ChainedTranscriptClient
from youtube_market_brief.domain.types import Transcript, TranscriptSkip


class _StubClient:
    def __init__(self, result):
        self.result = result
        self.calls: list[str] = []

    def fetch(self, video_id: str):
        self.calls.append(video_id)
        return self.result


def _transcript(video_id: str = "abc123xyz89") -> Transcript:
    return Transcript(
        video_id=video_id,
        language="ko",
        is_auto_generated=True,
        segments=(),
        full_text="hello",
        char_count=5,
        fetched_at=datetime(2026, 5, 13, tzinfo=UTC),
    )


def test_chained_transcript_client_falls_back_on_ip_blocked():
    first = _StubClient(TranscriptSkip("abc123xyz89", "ip_blocked", "blocked"))
    second = _StubClient(_transcript())

    result = ChainedTranscriptClient([("first", first), ("second", second)]).fetch(
        "abc123xyz89"
    )

    assert isinstance(result, Transcript)
    assert first.calls == ["abc123xyz89"]
    assert second.calls == ["abc123xyz89"]


def test_chained_transcript_client_can_reach_stt_fallback_after_two_retryable_skips():
    first = _StubClient(TranscriptSkip("abc123xyz89", "api_changed", "429"))
    second = _StubClient(TranscriptSkip("abc123xyz89", "ip_blocked", "blocked"))
    third = _StubClient(_transcript())

    result = ChainedTranscriptClient(
        [("yt_dlp", first), ("youtube_transcript_api", second), ("openai_stt", third)]
    ).fetch("abc123xyz89")

    assert isinstance(result, Transcript)
    assert first.calls == ["abc123xyz89"]
    assert second.calls == ["abc123xyz89"]
    assert third.calls == ["abc123xyz89"]


def test_chained_transcript_client_stops_on_no_captions():
    first = _StubClient(TranscriptSkip("abc123xyz89", "no_captions", "none"))
    second = _StubClient(_transcript())

    result = ChainedTranscriptClient([("first", first), ("second", second)]).fetch(
        "abc123xyz89"
    )

    assert isinstance(result, TranscriptSkip)
    assert result.reason == "no_captions"
    assert second.calls == []
