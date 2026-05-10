"""Unit tests for OpenAIAPIClient.

Mocks the openai SDK so no network calls are made.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from youtube_market_brief._clients.llm import (
    LLMCallError,
    LLMResponse,
    OpenAIAPIClient,
)


def _fake_completion(text: str, *, completion_id: str = "chatcmpl-test001"):
    """Build an openai ChatCompletion-shaped object."""
    message = SimpleNamespace(content=text)
    choice = SimpleNamespace(message=message, finish_reason="stop")
    usage = SimpleNamespace(prompt_tokens=100, completion_tokens=50)
    return SimpleNamespace(
        id=completion_id,
        model="gpt-4o",
        choices=[choice],
        usage=usage,
    )


def test_call_returns_text_and_metadata():
    fake_resp = _fake_completion('```json\n{"ok": true}\n```')
    fake_sdk = MagicMock()
    fake_sdk.chat.completions.create.return_value = fake_resp

    with patch("youtube_market_brief._clients.llm.openai") as mock_openai:
        mock_openai.OpenAI.return_value = fake_sdk
        client = OpenAIAPIClient(api_key="sk-test")
        resp = client.call(system="SYS", user="USR", timeout_sec=30)

    assert isinstance(resp, LLMResponse)
    assert '"ok": true' in resp.text
    assert resp.session_id == "chatcmpl-test001"
    assert resp.duration_ms >= 0
    assert resp.raw_envelope["usage"]["prompt_tokens"] == 100


def test_call_sends_system_and_user_messages():
    fake_sdk = MagicMock()
    fake_sdk.chat.completions.create.return_value = _fake_completion("ok")

    with patch("youtube_market_brief._clients.llm.openai") as mock_openai:
        mock_openai.OpenAI.return_value = fake_sdk
        client = OpenAIAPIClient(api_key="sk-test")
        client.call(system="SYS", user="USR", timeout_sec=30)

    kwargs = fake_sdk.chat.completions.create.call_args.kwargs
    messages = kwargs["messages"]
    assert messages[0] == {"role": "system", "content": "SYS"}
    assert messages[1] == {"role": "user", "content": "USR"}


def test_call_uses_configured_model_and_max_tokens():
    fake_sdk = MagicMock()
    fake_sdk.chat.completions.create.return_value = _fake_completion("ok")

    with patch("youtube_market_brief._clients.llm.openai") as mock_openai:
        mock_openai.OpenAI.return_value = fake_sdk
        client = OpenAIAPIClient(api_key="sk-test", model="gpt-4o-mini", max_tokens=2048)
        client.call(system="SYS", user="USR", timeout_sec=30)

    kwargs = fake_sdk.chat.completions.create.call_args.kwargs
    assert kwargs["model"] == "gpt-4o-mini"
    assert kwargs["max_tokens"] == 2048


def test_call_passes_timeout():
    fake_sdk = MagicMock()
    fake_sdk.chat.completions.create.return_value = _fake_completion("ok")

    with patch("youtube_market_brief._clients.llm.openai") as mock_openai:
        mock_openai.OpenAI.return_value = fake_sdk
        client = OpenAIAPIClient(api_key="sk-test")
        client.call(system="SYS", user="USR", timeout_sec=42)

    kwargs = fake_sdk.chat.completions.create.call_args.kwargs
    assert kwargs["timeout"] == 42.0


def test_call_raises_on_empty_text():
    message = SimpleNamespace(content="")
    choice = SimpleNamespace(message=message, finish_reason="stop")
    usage = SimpleNamespace(prompt_tokens=10, completion_tokens=0)
    empty = SimpleNamespace(id="chatcmpl-empty", model="gpt-4o", choices=[choice], usage=usage)

    fake_sdk = MagicMock()
    fake_sdk.chat.completions.create.return_value = empty

    with patch("youtube_market_brief._clients.llm.openai") as mock_openai:
        mock_openai.OpenAI.return_value = fake_sdk
        client = OpenAIAPIClient(api_key="sk-test")
        with pytest.raises(LLMCallError):
            client.call(system="SYS", user="USR", timeout_sec=30)


def test_health_check_ok():
    fake_sdk = MagicMock()
    fake_sdk.chat.completions.create.return_value = _fake_completion("OK")

    with patch("youtube_market_brief._clients.llm.openai") as mock_openai:
        mock_openai.OpenAI.return_value = fake_sdk
        client = OpenAIAPIClient(api_key="sk-test")
        assert client.health_check() is True


def test_health_check_failure_returns_false():
    fake_sdk = MagicMock()
    fake_sdk.chat.completions.create.side_effect = RuntimeError("auth failed")

    with patch("youtube_market_brief._clients.llm.openai") as mock_openai:
        mock_openai.OpenAI.return_value = fake_sdk
        client = OpenAIAPIClient(api_key="sk-bad")
        assert client.health_check() is False


def test_default_model_is_gpt4o():
    with patch("youtube_market_brief._clients.llm.openai") as mock_openai:
        mock_openai.OpenAI.return_value = MagicMock()
        client = OpenAIAPIClient(api_key="sk-test")
        assert client.model == "gpt-4o"
