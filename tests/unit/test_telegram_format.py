from youtube_market_brief.domain.telegram_format import SOFT_CAP, split_message


def test_split_short_message_returns_one():
    assert split_message("hello") == ["hello"]


def test_split_long_message_breaks_at_paragraphs():
    long = ("문장 " * 300 + "\n\n") * 5
    chunks = split_message(long)
    assert len(chunks) >= 2
    assert all(len(c) <= SOFT_CAP + 32 for c in chunks)


def test_split_appends_pagination_suffix():
    long = ("문장 " * 300 + "\n\n") * 5
    chunks = split_message(long)
    if len(chunks) > 1:
        assert "(1/" in chunks[0]
        assert f"({len(chunks)}/{len(chunks)})" in chunks[-1]


def test_split_extreme_single_long_line():
    long = "x" * (SOFT_CAP * 2 + 100)
    chunks = split_message(long)
    assert len(chunks) >= 2
