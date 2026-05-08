from __future__ import annotations

from youtube_market_brief.domain.types import Transcript, TranscriptSkip


class FakeTranscriptClient:
    def __init__(self, mapping: dict[str, Transcript | TranscriptSkip]):
        self._mapping = mapping
        self.calls: list[str] = []

    def fetch(self, video_id: str) -> Transcript | TranscriptSkip:
        self.calls.append(video_id)
        return self._mapping[video_id]
