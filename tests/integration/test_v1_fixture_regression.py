"""Integration regression — v1 fixtures pass strict schema validation + parse.

These fixtures are real LLM outputs from synthetic transcripts (Task 12 of P1).
They guard against schema regressions in the analyze parser + downstream
domain types.
"""

import json
from pathlib import Path

import pytest

from youtube_market_brief.pipeline.analyze import _parse_video_payload

FIXTURE_DIR = (
    Path(__file__).parent.parent / "fixtures" / "analyze_outputs" / "v1"
)


@pytest.mark.parametrize(
    "fixture_file", sorted(FIXTURE_DIR.glob("*.json")), ids=lambda p: p.stem
)
def test_v1_fixture_passes_strict_validation(fixture_file):
    """All v1 fixtures must pass strict schema validation."""
    payload = json.loads(fixture_file.read_text(encoding="utf-8"))
    parsed = _parse_video_payload(payload)
    assert "key_insights" in parsed
    assert len(parsed["key_insights"]) >= 3


@pytest.mark.parametrize(
    "fixture_file", sorted(FIXTURE_DIR.glob("*.json")), ids=lambda p: p.stem
)
def test_v1_fixture_insights_are_objects_with_required_keys(fixture_file):
    payload = json.loads(fixture_file.read_text(encoding="utf-8"))
    for i, ki in enumerate(payload["key_insights"]):
        assert isinstance(ki, dict), f"key_insights[{i}] not object in {fixture_file.name}"
        assert "text" in ki
        assert "sector_tags" in ki
        assert "theme_tags" in ki


@pytest.mark.parametrize(
    "fixture_file", sorted(FIXTURE_DIR.glob("*.json")), ids=lambda p: p.stem
)
def test_v1_fixture_red_team_are_objects_with_required_keys(fixture_file):
    payload = json.loads(fixture_file.read_text(encoding="utf-8"))
    for i, rt in enumerate(payload["red_team"]):
        assert isinstance(rt, dict), f"red_team[{i}] not object in {fixture_file.name}"
        assert "text" in rt
        assert "sector_tags" in rt
        assert "theme_tags" in rt


@pytest.mark.parametrize(
    "fixture_file", sorted(FIXTURE_DIR.glob("*.json")), ids=lambda p: p.stem
)
def test_v1_fixture_tickers_have_sector_tag_field(fixture_file):
    payload = json.loads(fixture_file.read_text(encoding="utf-8"))
    for i, t in enumerate(payload["tickers"]):
        assert "sector_tag" in t, f"tickers[{i}] missing sector_tag in {fixture_file.name}"
