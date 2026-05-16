import logging

from youtube_market_brief.logging_setup import SecretRedactionFilter


def test_secret_redaction_filter_masks_common_tokens():
    record = logging.LogRecord(
        name="x",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=(
            "OPENAI_API_KEY=sk-test "
            "https://api.telegram.org/bot123456:abcDEF/sendMessage "
            "Authorization: Bearer token.value "
            "SAPISID=cookievalue"
        ),
        args=(),
        exc_info=None,
    )

    SecretRedactionFilter().filter(record)

    assert "sk-test" not in record.msg
    assert "123456:abcDEF" not in record.msg
    assert "token.value" not in record.msg
    assert "cookievalue" not in record.msg
    assert "OPENAI_API_KEY=<redacted>" in record.msg
