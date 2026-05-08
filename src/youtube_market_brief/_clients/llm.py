"""LLM client — `claude` CLI subprocess. Anthropic API key NOT used.

Why subprocess: the user's vault Runner pattern (see ~/vault/Harness/runners/wiki_evaluator.yaml)
invokes `claude` directly. This reuses the Claude Code login session — no
separate API key, no separate billing. The subprocess interface is:

    claude -p \
        --model sonnet \
        --output-format json \
        --permission-mode bypassPermissions \
        --max-turns 1
    < prompt_text  (via stdin)

Output is a JSON envelope; `result["result"]` is the model's response text,
which should contain a fenced ```json ... ``` block matching the per-prompt
schema. We extract and parse that.
"""

from __future__ import annotations

import json
import re
import subprocess
import time
from dataclasses import dataclass
from typing import Protocol

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
