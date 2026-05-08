"""Unit tests for AnthropicAPIClient.

Mocks the anthropic SDK so no network calls are made.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from youtube_market_brief._clients.llm import (
    AnthropicAPIClient,
    LLMCallError,
    LLMResponse,
)


def _fake_message(text: str, *, msg_id: str = "msg_test_001"):
    """Build an anthropic Message-shaped object."""
    block = SimpleNamespace(type="text", text=text)
    usage = SimpleNamespace(
        input_tokens=100,
        output_tokens=50,
        cache_creation_input_tokens=0,
        cache_read_input_tokens=0,
    )
    return SimpleNamespace(
        id=msg_id,
        model="claude-sonnet-4-6",
        stop_reason="end_turn",
        content=[block],
        usage=usage,
    )


def test_call_returns_text_and_metadata():
    fake_resp = _fake_message('```json\n{"ok": true}\n```')
    fake_sdk = MagicMock()
    fake_sdk.with_options.return_value = fake_sdk
    fake_sdk.messages.create.return_value = fake_resp

    with patch("youtube_market_brief._clients.llm.anthropic") as mock_anth:
        mock_anth.Anthropic.return_value = fake_sdk
        client = AnthropicAPIClient(api_key="sk-test")
        resp = client.call(system="SYS", user="USR", timeout_sec=30)

    assert isinstance(resp, LLMResponse)
    assert '"ok": true' in resp.text
    assert resp.session_id == "msg_test_001"
    assert resp.duration_ms >= 0
    assert resp.raw_envelope["usage"]["input_tokens"] == 100


def test_call_sends_cache_control_on_system_prompt():
    """System prompt must carry cache_control: ephemeral so repeated calls hit cache."""
    fake_sdk = MagicMock()
    fake_sdk.with_options.return_value = fake_sdk
    fake_sdk.messages.create.return_value = _fake_message("ok")

    with patch("youtube_market_brief._clients.llm.anthropic") as mock_anth:
        mock_anth.Anthropic.return_value = fake_sdk
        client = AnthropicAPIClient(api_key="sk-test")
        client.call(system="SYS", user="USR", timeout_sec=30)

    kwargs = fake_sdk.messages.create.call_args.kwargs
    system = kwargs["system"]
    assert isinstance(system, list)
    assert system[0]["type"] == "text"
    assert system[0]["text"] == "SYS"
    assert system[0]["cache_control"] == {"type": "ephemeral"}


def test_call_uses_configured_model_and_max_tokens():
    fake_sdk = MagicMock()
    fake_sdk.with_options.return_value = fake_sdk
    fake_sdk.messages.create.return_value = _fake_message("ok")

    with patch("youtube_market_brief._clients.llm.anthropic") as mock_anth:
        mock_anth.Anthropic.return_value = fake_sdk
        client = AnthropicAPIClient(
            api_key="sk-test", model="claude-haiku-4-5", max_tokens=2048
        )
        client.call(system="SYS", user="USR", timeout_sec=30)

    kwargs = fake_sdk.messages.create.call_args.kwargs
    assert kwargs["model"] == "claude-haiku-4-5"
    assert kwargs["max_tokens"] == 2048
    assert kwargs["messages"] == [{"role": "user", "content": "USR"}]


def test_call_applies_timeout_via_with_options():
    fake_sdk = MagicMock()
    fake_sdk.with_options.return_value = fake_sdk
    fake_sdk.messages.create.return_value = _fake_message("ok")

    with patch("youtube_market_brief._clients.llm.anthropic") as mock_anth:
        mock_anth.Anthropic.return_value = fake_sdk
        client = AnthropicAPIClient(api_key="sk-test")
        client.call(system="SYS", user="USR", timeout_sec=42)

    fake_sdk.with_options.assert_called_with(timeout=42.0)


def test_call_raises_on_empty_text():
    empty = SimpleNamespace(
        id="msg",
        model="claude-sonnet-4-6",
        stop_reason="end_turn",
        content=[],
        usage=SimpleNamespace(
            input_tokens=10,
            output_tokens=0,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=0,
        ),
    )
    fake_sdk = MagicMock()
    fake_sdk.with_options.return_value = fake_sdk
    fake_sdk.messages.create.return_value = empty

    with patch("youtube_market_brief._clients.llm.anthropic") as mock_anth:
        mock_anth.Anthropic.return_value = fake_sdk
        client = AnthropicAPIClient(api_key="sk-test")
        with pytest.raises(LLMCallError):
            client.call(system="SYS", user="USR", timeout_sec=30)


def test_health_check_pong():
    fake_sdk = MagicMock()
    fake_sdk.with_options.return_value = fake_sdk
    fake_sdk.messages.create.return_value = _fake_message("PONG")

    with patch("youtube_market_brief._clients.llm.anthropic") as mock_anth:
        mock_anth.Anthropic.return_value = fake_sdk
        client = AnthropicAPIClient(api_key="sk-test")
        assert client.health_check() is True


def test_health_check_failure_returns_false():
    fake_sdk = MagicMock()
    fake_sdk.with_options.return_value = fake_sdk
    fake_sdk.messages.create.side_effect = RuntimeError("auth failed")

    with patch("youtube_market_brief._clients.llm.anthropic") as mock_anth:
        mock_anth.Anthropic.return_value = fake_sdk
        client = AnthropicAPIClient(api_key="sk-bad")
        assert client.health_check() is False


def test_default_model_is_sonnet_4_6():
    """Preserve the original `--model sonnet` design intent."""
    with patch("youtube_market_brief._clients.llm.anthropic") as mock_anth:
        mock_anth.Anthropic.return_value = MagicMock()
        client = AnthropicAPIClient(api_key="sk-test")
        assert client.model == "claude-sonnet-4-6"
