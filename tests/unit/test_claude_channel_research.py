"""Unit tests for claude_channel_research script."""
from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import claude_channel_research as ccr  # noqa: E402

from youtube_market_brief.domain.types import (  # noqa: E402
    Segment,
    Transcript,
    TranscriptSkip,
    VideoMeta,
)
from tests.fakes import (  # noqa: E402
    FakeLLMClient,
    FakeTranscriptClient,
    FakeYouTubeClient,
)


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_video(video_id: str = "abc123", title: str = "Test Video") -> VideoMeta:
    return VideoMeta(
        video_id=video_id,
        channel_id="UCxxx",
        channel_name="Claude",
        channel_slug="claude",
        title=title,
        published_at_utc=datetime(2026, 3, 15, 10, 0, 0, tzinfo=UTC),
        url=f"https://youtu.be/{video_id}",
        duration_sec=600,
    )


def _make_transcript(video_id: str = "abc123", text: str = "hello world") -> Transcript:
    return Transcript(
        video_id=video_id,
        language="en",
        is_auto_generated=True,
        segments=(Segment(start=0.0, duration=1.0, text=text),),
        full_text=text,
        char_count=len(text),
        fetched_at=datetime.now(tz=UTC),
    )


_NOTE_JSON = """\
```json
{
  "summary": "Claude agents use tool loops",
  "key_insights": ["Tool use enables agents", "Streaming reduces latency"],
  "agent_patterns": [
    {"pattern": "Tool Loop", "description": "Agent calls tools repeatedly", "applicability": "Apply to PAS Runner"}
  ],
  "api_techniques": ["streaming with tool_use"],
  "mcp_relevance": ["expose tools as MCP resources"],
  "claude_code_tips": ["use subagents for parallel work"],
  "caution": ["don't loop without exit condition"]
}
```"""

_SYNTHESIS_JSON = """\
```json
{
  "top_patterns": ["Tool Loop pattern seen in 3 videos"],
  "quick_wins": ["Add streaming to PAS LLM calls"],
  "mcp_design_insights": ["Expose domain objects as MCP resources"],
  "claude_code_insights": ["Use parallel subagents for independent tasks"],
  "longer_term": ["Full agent memory architecture"]
}
```"""


# ── parse_video_note ──────────────────────────────────────────────────────────

def test_parse_video_note_happy_path():
    raw = {
        "summary": "Test summary",
        "key_insights": ["insight a", "insight b"],
        "agent_patterns": [{"pattern": "Loop", "description": "loops", "applicability": "PAS"}],
        "api_techniques": ["streaming"],
        "mcp_relevance": ["expose tools"],
        "claude_code_tips": ["use hooks"],
        "caution": ["avoid infinite loops"],
    }
    note = ccr.parse_video_note(
        raw,
        video_id="v1",
        title="T",
        url="https://youtu.be/v1",
        published_date="2026-03-15",
        transcript_chars=500,
    )
    assert note.video_id == "v1"
    assert note.summary == "Test summary"
    assert note.key_insights == ["insight a", "insight b"]
    assert len(note.agent_patterns) == 1
    assert note.agent_patterns[0].pattern == "Loop"
    assert note.transcript_chars == 500
    assert not note.was_skipped


def test_parse_video_note_empty_raw_gives_defaults():
    note = ccr.parse_video_note(
        {},
        video_id="v2",
        title="Empty",
        url="https://youtu.be/v2",
        published_date="2026-03-15",
        transcript_chars=0,
    )
    assert note.key_insights == []
    assert note.agent_patterns == []
    assert not note.was_skipped


def test_parse_synthesis_happy_path():
    raw = {
        "top_patterns": ["p1", "p2"],
        "quick_wins": ["qw1"],
        "mcp_design_insights": ["mcp1"],
        "claude_code_insights": ["cc1"],
        "longer_term": ["lt1"],
    }
    report = ccr.parse_synthesis(raw, videos_analyzed=5, videos_skipped=1)
    assert report.videos_analyzed == 5
    assert report.videos_skipped == 1
    assert report.top_patterns == ["p1", "p2"]
    assert report.quick_wins == ["qw1"]


# ── build_note_md ─────────────────────────────────────────────────────────────

def test_build_note_md_contains_frontmatter_and_sections():
    raw = {
        "summary": "Test summary",
        "key_insights": ["Insight A"],
        "agent_patterns": [{"pattern": "Tool Loop", "description": "loops", "applicability": "PAS"}],
        "api_techniques": ["streaming"],
        "mcp_relevance": [],
        "claude_code_tips": [],
        "caution": ["watch out"],
    }
    note = ccr.parse_video_note(
        raw,
        video_id="abc",
        title="My Video",
        url="https://youtu.be/abc",
        published_date="2026-03-15",
        transcript_chars=100,
    )
    md = ccr.build_note_md(note)
    assert "source_url: https://youtu.be/abc" in md
    assert "video_id: abc" in md
    assert "# My Video" in md
    assert "Insight A" in md
    assert "Tool Loop" in md
    assert "watch out" in md


def test_build_note_md_skipped_shows_reason():
    note = ccr.VideoResearchNote(
        video_id="x",
        title="Skip me",
        url="https://youtu.be/x",
        published_date="2026-03-15",
        summary="",
        key_insights=[],
        agent_patterns=[],
        api_techniques=[],
        mcp_relevance=[],
        claude_code_tips=[],
        caution=[],
        transcript_chars=0,
        was_skipped=True,
        skip_reason="transcript:no_captions",
    )
    md = ccr.build_note_md(note)
    assert "Skipped" in md
    assert "no_captions" in md


def test_build_synthesis_md_all_sections_present():
    report = ccr.parse_synthesis(
        {
            "top_patterns": ["p1"],
            "quick_wins": ["q1"],
            "mcp_design_insights": ["m1"],
            "claude_code_insights": ["c1"],
            "longer_term": ["l1"],
        },
        videos_analyzed=3,
        videos_skipped=1,
    )
    md = ccr.build_synthesis_md(report)
    assert "Top Patterns" in md
    assert "Quick Wins" in md
    assert "MCP Design Insights" in md
    assert "Claude Code Insights" in md
    assert "Longer-Term" in md
    assert "**Videos analyzed:** 3" in md
    assert "p1" in md


# ── analyze_transcript ────────────────────────────────────────────────────────

def test_analyze_transcript_ok():
    video = _make_video("abc123")
    transcript = _make_transcript("abc123", "agents use tool loops " * 100)
    llm = FakeLLMClient(responder=lambda s, u: _NOTE_JSON)

    note = ccr.analyze_transcript(video, transcript, llm)

    assert not note.was_skipped
    assert note.summary == "Claude agents use tool loops"
    assert len(note.agent_patterns) == 1
    assert note.agent_patterns[0].pattern == "Tool Loop"
    assert len(llm.calls) == 1


def test_analyze_transcript_caps_input_at_12000_chars():
    video = _make_video("big1")
    long_text = "word " * 5000
    transcript = _make_transcript("big1", long_text)
    llm = FakeLLMClient(responder=lambda s, u: _NOTE_JSON)

    ccr.analyze_transcript(video, transcript, llm)

    _, user_input = llm.calls[0]
    assert len(user_input) <= 12_000


def test_analyze_transcript_returns_skipped_on_transcript_skip():
    video = _make_video("skip1")
    skip = TranscriptSkip(video_id="skip1", reason="no_captions", detail="")
    llm = FakeLLMClient(responder=lambda s, u: _NOTE_JSON)

    note = ccr.analyze_transcript(video, skip, llm)

    assert note.was_skipped
    assert "no_captions" in note.skip_reason
    assert len(llm.calls) == 0


def test_analyze_transcript_returns_skipped_on_llm_error():
    from youtube_market_brief._clients.llm import LLMCallError

    video = _make_video("fail1")
    transcript = _make_transcript("fail1", "some content")

    def raise_error(s, u):
        raise LLMCallError("boom")

    llm = FakeLLMClient(responder=raise_error)
    note = ccr.analyze_transcript(video, transcript, llm)

    assert note.was_skipped
    assert "llm_error" in note.skip_reason


# ── write_note_file / write_synthesis_file ────────────────────────────────────

def test_write_note_file_creates_correctly_named_file(tmp_path):
    note = ccr.VideoResearchNote(
        video_id="xyz",
        title="Write Test",
        url="https://youtu.be/xyz",
        published_date="2026-03-15",
        summary="test",
        key_insights=["I1"],
        agent_patterns=[],
        api_techniques=[],
        mcp_relevance=[],
        claude_code_tips=[],
        caution=[],
        transcript_chars=100,
    )
    path = ccr.write_note_file(note, tmp_path)

    assert path.exists()
    assert path.name == "2026-03-15_xyz.md"
    content = path.read_text()
    assert "Write Test" in content
    assert "I1" in content


def test_write_note_file_creates_output_dir_if_missing(tmp_path):
    note = ccr.VideoResearchNote(
        video_id="new1",
        title="T",
        url="https://youtu.be/new1",
        published_date="2026-03-15",
        summary="s",
        key_insights=[],
        agent_patterns=[],
        api_techniques=[],
        mcp_relevance=[],
        claude_code_tips=[],
        caution=[],
        transcript_chars=0,
    )
    nested = tmp_path / "deep" / "nested"
    path = ccr.write_note_file(note, nested)
    assert path.exists()


def test_write_synthesis_file_creates_correctly_named_file(tmp_path):
    report = ccr.parse_synthesis(
        {
            "top_patterns": ["p1"],
            "quick_wins": [],
            "mcp_design_insights": [],
            "claude_code_insights": [],
            "longer_term": [],
        },
        videos_analyzed=2,
        videos_skipped=0,
    )
    path = ccr.write_synthesis_file(report, tmp_path)

    assert path.exists()
    assert path.name.startswith("_synthesis_")
    assert path.name.endswith(".md")
    assert "p1" in path.read_text()


# ── run_research ──────────────────────────────────────────────────────────────

def _responder(note_json: str, synthesis_json: str):
    def _fn(system: str, user: str) -> str:
        if "Synthesize research notes" in system:
            return synthesis_json
        return note_json
    return _fn


def test_run_research_processes_two_videos(tmp_path):
    videos = [_make_video("v1", "Video One"), _make_video("v2", "Video Two")]
    yt = FakeYouTubeClient(
        handle_to_id={"@claude": "UCtest"},
        videos_by_channel={"UCtest": videos},
    )
    transcript = FakeTranscriptClient({
        "v1": _make_transcript("v1", "content one"),
        "v2": _make_transcript("v2", "content two"),
    })
    llm = FakeLLMClient(responder=_responder(_NOTE_JSON, _SYNTHESIS_JSON))

    report = ccr.run_research(
        channel_handle="@claude",
        published_after=datetime(2025, 11, 1, tzinfo=UTC),
        max_videos=10,
        output_dir=tmp_path,
        yt_client=yt,
        transcript_client=transcript,
        llm_client=llm,
    )

    assert report.videos_analyzed == 2
    assert report.videos_skipped == 0
    assert (tmp_path / "2026-03-15_v1.md").exists()
    assert (tmp_path / "2026-03-15_v2.md").exists()
    assert len(list(tmp_path.glob("_synthesis_*.md"))) == 1


def test_run_research_counts_skipped_transcripts(tmp_path):
    videos = [_make_video("v1"), _make_video("v2")]
    yt = FakeYouTubeClient(
        handle_to_id={"@claude": "UCtest"},
        videos_by_channel={"UCtest": videos},
    )
    transcript = FakeTranscriptClient({
        "v1": _make_transcript("v1", "content"),
        "v2": TranscriptSkip(video_id="v2", reason="no_captions", detail=""),
    })
    llm = FakeLLMClient(responder=_responder(_NOTE_JSON, _SYNTHESIS_JSON))

    report = ccr.run_research(
        channel_handle="@claude",
        published_after=datetime(2025, 11, 1, tzinfo=UTC),
        max_videos=10,
        output_dir=tmp_path,
        yt_client=yt,
        transcript_client=transcript,
        llm_client=llm,
    )

    assert report.videos_analyzed == 1
    assert report.videos_skipped == 1


def test_run_research_aborts_on_unresolvable_channel(tmp_path):
    yt = FakeYouTubeClient(handle_to_id={}, videos_by_channel={})
    transcript = FakeTranscriptClient({})
    llm = FakeLLMClient(responder=lambda s, u: "")

    with pytest.raises(ValueError, match="Could not resolve channel_id"):
        ccr.run_research(
            channel_handle="@nonexistent",
            published_after=datetime(2025, 11, 1, tzinfo=UTC),
            max_videos=10,
            output_dir=tmp_path,
            yt_client=yt,
            transcript_client=transcript,
            llm_client=llm,
        )
