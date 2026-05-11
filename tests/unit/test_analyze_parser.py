import json
from pathlib import Path

import pytest

from youtube_market_brief.pipeline.analyze import _parse_video_payload


FIXTURE = (
    Path(__file__).parent.parent
    / "fixtures"
    / "analyze_outputs"
    / "handcrafted"
    / "v1_minimal.json"
)


def test_parse_v1_payload_returns_dict_with_object_insights():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    parsed = _parse_video_payload(payload)
    assert isinstance(parsed["key_insights"][0], dict)
    assert parsed["key_insights"][0]["text"] == "AI capex 가속"
    assert parsed["key_insights"][0]["sector_tags"] == ["semiconductors"]


def test_parse_v1_payload_validates_red_team_objects():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    parsed = _parse_video_payload(payload)
    assert parsed["red_team"][0]["text"] == "capex ROI 의심"


def test_parse_rejects_string_key_insights_legacy():
    payload = {
        "headline_3line": ["a", "b", "c"],
        "key_insights": ["plain string", "another", "third"],
        "red_team": [{"text": "x", "sector_tags": [], "theme_tags": []}],
        "tickers": [],
        "watchlist_hits": [],
    }
    with pytest.raises(ValueError, match="key_insights"):
        _parse_video_payload(payload)


def test_parse_rejects_invalid_sector_enum():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["key_insights"][0]["sector_tags"] = ["bogus_sector"]
    with pytest.raises(ValueError, match="sector_tags"):
        _parse_video_payload(payload)


def test_parse_rejects_invalid_theme_enum():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["red_team"][0]["theme_tags"] = ["bogus_theme"]
    with pytest.raises(ValueError, match="theme_tags"):
        _parse_video_payload(payload)


def test_parse_rejects_whitespace_padded_slug():
    """Trailing/leading whitespace in slug is a contract violation — parser must reject."""
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["key_insights"][0]["sector_tags"] = ["semiconductors "]  # trailing space
    with pytest.raises(ValueError, match="sector_tags"):
        _parse_video_payload(payload)


def test_parse_allows_empty_tag_arrays():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["key_insights"][0]["sector_tags"] = []
    payload["key_insights"][0]["theme_tags"] = []
    parsed = _parse_video_payload(payload)
    assert parsed["key_insights"][0]["sector_tags"] == []


def test_parse_rejects_invalid_ticker_sector_tag():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["tickers"][0]["sector_tag"] = "bogus_sector"
    with pytest.raises(ValueError, match="sector_tag"):
        _parse_video_payload(payload)


def test_parse_allows_null_ticker_sector_tag():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["tickers"][0]["sector_tag"] = None
    parsed = _parse_video_payload(payload)
    assert parsed["tickers"][0]["sector_tag"] is None
