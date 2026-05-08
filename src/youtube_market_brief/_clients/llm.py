"""LLM client adapters.

Two implementations of the LLMClient Protocol:

- `ClaudeCLIClient`: invokes the `claude` CLI subprocess. Reuses the user's
  Claude Code login session — no separate API key. Local-only (CLI must be
  installed and authed). Suited for laptop runs.

- `AnthropicAPIClient`: calls the Anthropic Messages API directly using the
  official SDK. Requires `ANTHROPIC_API_KEY`. Runs anywhere — used by the
  cloud cron workflow. Applies prompt caching on the system prompt, since
  the same system prompt is reused across many per-video calls in one run.

Both return responses whose `.text` contains a fenced ```json ... ``` block
matching the per-prompt schema. The pipeline parses that with `extract_fenced_json`.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import time
from dataclasses import dataclass
from typing import Protocol

import anthropic

log = logging.getLogger(__name__)

_FENCED_JSON = re.compile(r"```(?:json)?\s*\n(.+?)\n```", re.DOTALL)


@dataclass
class LLMResponse:
    text: str
    raw_envelope: dict
    duration_ms: int
    session_id: str | None


class LLMClient(Protocol):
    def health_check(self) -> bool: ...
    def call(self, *, system: str, user: str, timeout_sec: int) -> LLMResponse: ...


class ClaudeCLIClient:
    def __init__(
        self,
        *,
        bin_path: str = "claude",
        model: str = "sonnet",
        permission_mode: str = "bypassPermissions",
    ):
        self.bin_path = bin_path
        self.model = model
        self.permission_mode = permission_mode

    def health_check(self) -> bool:
        """Run a tiny ping prompt to verify CLI + auth work."""
        try:
            self.call(system="You only respond with the word PONG.", user="ping", timeout_sec=30)
            return True
        except Exception:
            return False

    def call(self, *, system: str, user: str, timeout_sec: int) -> LLMResponse:
        """Single-turn call. system + user concatenated as one prompt block."""
        prompt = f"<system>\n{system}\n</system>\n\n<user>\n{user}\n</user>\n"
        cmd = [
            self.bin_path,
            "-p",
            "--model", self.model,
            "--output-format", "json",
            "--permission-mode", self.permission_mode,
            "--max-turns", "1",
        ]
        t0 = time.monotonic()
        proc = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
        )
        duration_ms = int((time.monotonic() - t0) * 1000)
        if proc.returncode != 0:
            raise LLMCallError(
                f"claude CLI exit {proc.returncode}: {proc.stderr.strip()[:500]}"
            )
        try:
            envelope = json.loads(proc.stdout)
        except json.JSONDecodeError as e:
            raise LLMCallError(f"claude CLI output not JSON: {e}; head={proc.stdout[:200]}") from e
        text = envelope.get("result") or envelope.get("text") or ""
        if not text:
            raise LLMCallError(f"claude CLI envelope missing 'result': keys={list(envelope.keys())}")
        return LLMResponse(
            text=text,
            raw_envelope=envelope,
            duration_ms=duration_ms,
            session_id=envelope.get("session_id"),
        )


class LLMCallError(RuntimeError):
    pass


class AnthropicAPIClient:
    """LLM client backed by the Anthropic Messages API.

    Used by the cloud cron workflow where the `claude` CLI is not available.
    The system prompt is cached (`cache_control: ephemeral`) — the per-video
    pipeline reuses the same system prompt across many calls in one run, so
    after the first call the prefix is served from cache (~10% of input cost).

    Default model is `claude-sonnet-4-6`, preserving the original
    `--model sonnet` choice that drove the local CLI client.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = "claude-sonnet-4-6",
        max_tokens: int = 8192,
    ):
        self.model = model
        self.max_tokens = max_tokens
        self._client = anthropic.Anthropic(api_key=api_key)

    def health_check(self) -> bool:
        try:
            client = self._client.with_options(timeout=30.0)
            resp = client.messages.create(
                model=self.model,
                max_tokens=16,
                messages=[{"role": "user", "content": "Reply with just one word: PONG"}],
            )
            text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
            return "PONG" in text.upper()
        except Exception as e:
            log.warning("AnthropicAPIClient health_check failed: %s", e)
            return False

    def call(self, *, system: str, user: str, timeout_sec: int) -> LLMResponse:
        client = self._client.with_options(timeout=float(timeout_sec))
        t0 = time.monotonic()
        try:
            resp = client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=[
                    {
                        "type": "text",
                        "text": system,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": user}],
            )
        except anthropic.APIError as e:
            raise LLMCallError(f"Anthropic API error: {e}") from e
        duration_ms = int((time.monotonic() - t0) * 1000)
        text = "".join(
            b.text for b in resp.content if getattr(b, "type", None) == "text"
        )
        if not text:
            raise LLMCallError(
                f"Anthropic API returned no text content (stop_reason={resp.stop_reason})"
            )
        usage = resp.usage
        envelope = {
            "model": resp.model,
            "stop_reason": resp.stop_reason,
            "usage": {
                "input_tokens": getattr(usage, "input_tokens", 0),
                "output_tokens": getattr(usage, "output_tokens", 0),
                "cache_read_input_tokens": getattr(usage, "cache_read_input_tokens", 0),
                "cache_creation_input_tokens": getattr(usage, "cache_creation_input_tokens", 0),
            },
        }
        return LLMResponse(
            text=text,
            raw_envelope=envelope,
            duration_ms=duration_ms,
            session_id=resp.id,
        )


def extract_fenced_json(text: str) -> dict | list:
    """Extract first ```json ... ``` block and parse. Raises ValueError on miss/error."""
    m = _FENCED_JSON.search(text)
    if not m:
        # Last-resort: try to find a top-level {...} block.
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end <= start:
            raise ValueError("no fenced JSON block and no balanced braces found")
        candidate = text[start : end + 1]
    else:
        candidate = m.group(1)
    return json.loads(candidate)
