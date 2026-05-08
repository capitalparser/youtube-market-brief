from __future__ import annotations

from collections.abc import Callable

from youtube_market_brief._clients.llm import LLMResponse


class FakeLLMClient:
    """Returns canned responses keyed off prompt content via `responder` callable.

    `responder(system, user) -> str` returns the model's text (already containing
    a fenced ```json ... ``` block, just like the real CLI).
    """

    def __init__(self, *, responder: Callable[[str, str], str], healthy: bool = True):
        self._responder = responder
        self._healthy = healthy
        self.calls: list[tuple[str, str]] = []

    def health_check(self) -> bool:
        return self._healthy

    def call(self, *, system: str, user: str, timeout_sec: int) -> LLMResponse:
        self.calls.append((system, user))
        text = self._responder(system, user)
        return LLMResponse(
            text=text,
            raw_envelope={"result": text},
            duration_ms=10,
            session_id="fake-session",
        )
