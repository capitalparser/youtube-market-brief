from youtube_market_brief._clients.youtube_data import extract_video_id


def test_extract_video_id_accepts_raw_id():
    assert extract_video_id("EUzPgcabc12") == "EUzPgcabc12"


def test_extract_video_id_accepts_common_urls():
    assert extract_video_id("https://youtu.be/EUzPgcabc12?si=x") == "EUzPgcabc12"
    assert extract_video_id("https://www.youtube.com/watch?v=EUzPgcabc12") == "EUzPgcabc12"
    assert extract_video_id("https://www.youtube.com/live/EUzPgcabc12") == "EUzPgcabc12"
    assert extract_video_id("https://www.youtube.com/shorts/EUzPgcabc12") == "EUzPgcabc12"


def test_extract_video_id_rejects_invalid_values():
    assert extract_video_id("https://example.com/watch?v=EUzPgcabc12") is None
    assert extract_video_id("too-short") is None
