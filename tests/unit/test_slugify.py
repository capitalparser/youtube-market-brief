from youtube_market_brief.domain.slugify import channel_slug, video_slug


def test_channel_slug_prefers_hint():
    assert channel_slug("애경 투자노트", hint="aekyung_invest") == "aekyung_invest"


def test_channel_slug_normalizes_korean():
    s = channel_slug("애경 투자노트")
    assert "/" not in s
    assert s != ""


def test_channel_slug_strips_disallowed():
    assert "?" not in channel_slug("Bad?Channel/Name")


def test_channel_slug_fallback_to_hash_for_empty():
    s = channel_slug("???")
    assert len(s) == 8


def test_video_slug_includes_id_suffix():
    s = video_slug("FOMC 9월 인하 가능성", "abcdef123456")
    assert s.endswith("123456")


def test_video_slug_truncates_long_titles():
    long_title = "가" * 200
    s = video_slug(long_title, "videoid01234")
    assert len(s) <= 60 + 1 + 6  # base + dash + id_tail


def test_video_slug_handles_empty_title():
    s = video_slug("", "videoid01234")
    assert s.startswith("video-")
