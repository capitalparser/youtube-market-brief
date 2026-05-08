"""In-memory fakes for the four external clients (Protocol implementations)."""
from .fake_llm import FakeLLMClient
from .fake_telegram import FakeTelegramClient
from .fake_transcript import FakeTranscriptClient
from .fake_youtube import FakeYouTubeClient

__all__ = [
    "FakeLLMClient",
    "FakeTelegramClient",
    "FakeTranscriptClient",
    "FakeYouTubeClient",
]
