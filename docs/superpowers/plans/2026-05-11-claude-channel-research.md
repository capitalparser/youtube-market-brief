# Claude Channel Agent Research Script — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One-off script that fetches transcripts from the @claude YouTube channel (last 6 months), analyzes each with a custom agent-research prompt, and writes per-video vault notes + a synthesis report.

**Architecture:** Single script `scripts/claude_channel_research.py` that reuses the existing `_clients` (YouTube, transcript, LLM) and defines its own dataclasses + prompts inline. No new modules — all logic in one file to keep it self-contained and auditable.

**Tech Stack:** Python 3.12, `youtube_market_brief._clients.{youtube_data,transcript,llm}`, `youtube_market_brief.domain.types`, `pytest`, `uv run pytest`

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `scripts/claude_channel_research.py` | All script logic: models, prompts, analysis, output, CLI |
| Create | `tests/unit/test_claude_channel_research.py` | Unit tests for every function |

---

## Task 1: Data Models + JSON Parsing

**Files:**
- Create: `scripts/claude_channel_research.py` (skeleton + models + parse functions)
- Create: `tests/unit/test_claude_channel_research.py`

- [ ] **Step 1: Create the test file with parse tests**

Create `tests/unit/test_claude_channel_research.py`:

```python
"""Unit tests for claude_channel_research script."""
from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import claude_channel_research as ccr

from youtube_market_brief.domain.types import Segment, Transcript, TranscriptSkip, VideoMeta
from tests.fakes import FakeLLMClient, FakeTranscriptClient, FakeYouTubeClient


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
```

- [ ] **Step 2: Run the test to confirm it fails (ModuleNotFoundError expected)**

```bash
cd /Users/kjun/vault/01_Projects/01_youtube_market_brief
uv run pytest tests/unit/test_claude_channel_research.py::test_parse_video_note_happy_path -v
```

Expected: `ModuleNotFoundError: No module named 'claude_channel_research'`

- [ ] **Step 3: Create `scripts/claude_channel_research.py` with models + parse functions**

```python
#!/usr/bin/env python3
"""One-off research script: agent insights from the @claude YouTube channel."""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from youtube_market_brief._clients.llm import ClaudeCLIClient, LLMCallError, extract_fenced_json
from youtube_market_brief._clients.transcript import YouTubeTranscriptApiClient
from youtube_market_brief._clients.youtube_data import GoogleAPIYouTubeDataClient
from youtube_market_brief.domain.types import Transcript, TranscriptSkip, VideoMeta

log = logging.getLogger(__name__)

TRANSCRIPT_CHAR_CAP = 12_000


# ── Data models ───────────────────────────────────────────────────────────────

@dataclass
class AgentPattern:
    pattern: str
    description: str
    applicability: str


@dataclass
class VideoResearchNote:
    video_id: str
    title: str
    url: str
    published_date: str
    summary: str
    key_insights: list[str]
    agent_patterns: list[AgentPattern]
    api_techniques: list[str]
    mcp_relevance: list[str]
    claude_code_tips: list[str]
    caution: list[str]
    transcript_chars: int
    was_skipped: bool = False
    skip_reason: str = ""


@dataclass
class SynthesisReport:
    generated_date: str
    videos_analyzed: int
    videos_skipped: int
    top_patterns: list[str]
    quick_wins: list[str]
    mcp_design_insights: list[str]
    claude_code_insights: list[str]
    longer_term: list[str]


# ── JSON parsing ──────────────────────────────────────────────────────────────

def parse_video_note(
    raw: dict,
    *,
    video_id: str,
    title: str,
    url: str,
    published_date: str,
    transcript_chars: int,
) -> VideoResearchNote:
    patterns = [
        AgentPattern(
            pattern=p.get("pattern", ""),
            description=p.get("description", ""),
            applicability=p.get("applicability", ""),
        )
        for p in raw.get("agent_patterns", [])
        if isinstance(p, dict)
    ]
    return VideoResearchNote(
        video_id=video_id,
        title=title,
        url=url,
        published_date=published_date,
        summary=raw.get("summary", ""),
        key_insights=list(raw.get("key_insights", [])),
        agent_patterns=patterns,
        api_techniques=list(raw.get("api_techniques", [])),
        mcp_relevance=list(raw.get("mcp_relevance", [])),
        claude_code_tips=list(raw.get("claude_code_tips", [])),
        caution=list(raw.get("caution", [])),
        transcript_chars=transcript_chars,
    )


def parse_synthesis(
    raw: dict,
    *,
    videos_analyzed: int,
    videos_skipped: int,
) -> SynthesisReport:
    return SynthesisReport(
        generated_date=datetime.now(tz=UTC).strftime("%Y-%m-%d"),
        videos_analyzed=videos_analyzed,
        videos_skipped=videos_skipped,
        top_patterns=list(raw.get("top_patterns", [])),
        quick_wins=list(raw.get("quick_wins", [])),
        mcp_design_insights=list(raw.get("mcp_design_insights", [])),
        claude_code_insights=list(raw.get("claude_code_insights", [])),
        longer_term=list(raw.get("longer_term", [])),
    )
```

- [ ] **Step 4: Run parse tests — all should pass**

```bash
cd /Users/kjun/vault/01_Projects/01_youtube_market_brief
uv run pytest tests/unit/test_claude_channel_research.py -k "parse" -v
```

Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add scripts/claude_channel_research.py tests/unit/test_claude_channel_research.py
git commit -m "feat(research): scaffold claude channel research script — models + parse"
```

---

## Task 2: Markdown Rendering

**Files:**
- Modify: `scripts/claude_channel_research.py` (add `build_note_md`, `build_synthesis_md`)
- Modify: `tests/unit/test_claude_channel_research.py` (add MD rendering tests)

- [ ] **Step 1: Add rendering tests to the test file**

Append to `tests/unit/test_claude_channel_research.py`:

```python
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
    assert "Videos analyzed: 3" in md
    assert "p1" in md
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd /Users/kjun/vault/01_Projects/01_youtube_market_brief
uv run pytest tests/unit/test_claude_channel_research.py -k "build" -v
```

Expected: `AttributeError: module 'claude_channel_research' has no attribute 'build_note_md'`

- [ ] **Step 3: Add `build_note_md` and `build_synthesis_md` to the script**

Append to `scripts/claude_channel_research.py` (after `parse_synthesis`):

```python
# ── Markdown rendering ────────────────────────────────────────────────────────

def build_note_md(note: VideoResearchNote) -> str:
    today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
    lines = [
        "---",
        f"source_url: {note.url}",
        "source_type: youtube",
        f"captured_at: {today}",
        "channel: claude_official",
        f"video_id: {note.video_id}",
        "tags: [agent-research, claude-channel]",
        "---",
        "",
        f"# {note.title}",
        "",
        f"> {note.summary}" if note.summary else "",
        "",
    ]
    if note.was_skipped:
        lines.append(f"**Skipped:** {note.skip_reason}")
        return "\n".join(lines)

    if note.key_insights:
        lines += ["## Key Insights", ""]
        for insight in note.key_insights:
            lines.append(f"- {insight}")
        lines.append("")

    if note.agent_patterns:
        lines += ["## Agent Patterns", ""]
        for p in note.agent_patterns:
            lines += [f"### {p.pattern}", p.description, "", f"**Applicability:** {p.applicability}", ""]

    if note.api_techniques:
        lines += ["## Claude API Techniques", ""]
        for t in note.api_techniques:
            lines.append(f"- {t}")
        lines.append("")

    if note.mcp_relevance:
        lines += ["## MCP Relevance", ""]
        for r in note.mcp_relevance:
            lines.append(f"- {r}")
        lines.append("")

    if note.claude_code_tips:
        lines += ["## Claude Code Tips", ""]
        for t in note.claude_code_tips:
            lines.append(f"- {t}")
        lines.append("")

    if note.caution:
        lines += ["## Caution", ""]
        for c in note.caution:
            lines.append(f"- {c}")
        lines.append("")

    return "\n".join(lines)


def build_synthesis_md(report: SynthesisReport) -> str:
    lines = [
        f"# Claude Channel Agent Research — {report.generated_date}",
        "",
        f"**Videos analyzed:** {report.videos_analyzed}  ",
        f"**Videos skipped:** {report.videos_skipped}",
        "",
    ]
    for header, items in [
        ("## Top Patterns", report.top_patterns),
        ("## Quick Wins (Apply This Week)", report.quick_wins),
        ("## MCP Design Insights", report.mcp_design_insights),
        ("## Claude Code Insights", report.claude_code_insights),
        ("## Longer-Term", report.longer_term),
    ]:
        if items:
            lines += [header, ""]
            for item in items:
                lines.append(f"- {item}")
            lines.append("")

    return "\n".join(lines)
```

- [ ] **Step 4: Run rendering tests — all should pass**

```bash
cd /Users/kjun/vault/01_Projects/01_youtube_market_brief
uv run pytest tests/unit/test_claude_channel_research.py -k "build" -v
```

Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add scripts/claude_channel_research.py tests/unit/test_claude_channel_research.py
git commit -m "feat(research): add markdown rendering for notes and synthesis"
```

---

## Task 3: Transcript Analysis Wrapper

**Files:**
- Modify: `scripts/claude_channel_research.py` (add prompts + `analyze_transcript`)
- Modify: `tests/unit/test_claude_channel_research.py`

- [ ] **Step 1: Add `analyze_transcript` tests**

Append to `tests/unit/test_claude_channel_research.py`:

```python
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
    long_text = "word " * 5000  # 25000 chars
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
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd /Users/kjun/vault/01_Projects/01_youtube_market_brief
uv run pytest tests/unit/test_claude_channel_research.py -k "analyze" -v
```

Expected: `AttributeError: module 'claude_channel_research' has no attribute 'analyze_transcript'`

- [ ] **Step 3: Add prompts + `analyze_transcript` to the script**

Append to `scripts/claude_channel_research.py` (after `build_synthesis_md`):

```python
# ── Prompts ───────────────────────────────────────────────────────────────────

RESEARCH_SYSTEM_PROMPT = """\
You are analyzing a transcript from the Anthropic @claude YouTube channel.
Extract agent development insights relevant to:
1. Personal agent system (PAS) — Runner/Trigger/Sink architecture, orchestration patterns
2. MCP (Model Context Protocol) server design
3. Claude Code collaboration workflows (hooks, skills, subagents)

Return ONLY a fenced ```json block with this schema:
{
  "summary": "one sentence",
  "key_insights": ["3-5 concrete insights"],
  "agent_patterns": [
    {"pattern": "name", "description": "what it is", "applicability": "how it applies to PAS/MCP/Claude Code"}
  ],
  "api_techniques": ["specific Claude API techniques demonstrated"],
  "mcp_relevance": ["direct MCP server design applicability"],
  "claude_code_tips": ["Claude Code workflow improvements"],
  "caution": ["pitfalls or anti-patterns to avoid"]
}
If the video is not relevant to agent development, return empty arrays for all list fields.
Be specific and actionable."""

SYNTHESIS_SYSTEM_PROMPT = """\
Synthesize research notes from multiple @claude YouTube channel videos.
Identify cross-video patterns and produce actionable recommendations.

Return ONLY a fenced ```json block with this schema:
{
  "top_patterns": ["patterns in 2+ videos — most impactful first"],
  "quick_wins": ["apply this week — specific and actionable"],
  "mcp_design_insights": ["MCP server design takeaways"],
  "claude_code_insights": ["Claude Code workflow improvements"],
  "longer_term": ["patterns requiring deeper architectural work"]
}
Prioritize items appearing in 2+ videos. Include single-occurrence items only if highly actionable."""


# ── Analysis ──────────────────────────────────────────────────────────────────

def analyze_transcript(
    video: VideoMeta,
    result: Transcript | TranscriptSkip,
    llm,
) -> VideoResearchNote:
    published_date = video.published_at_utc.strftime("%Y-%m-%d")
    base = dict(
        video_id=video.video_id,
        title=video.title,
        url=video.url,
        published_date=published_date,
        summary="",
        key_insights=[],
        agent_patterns=[],
        api_techniques=[],
        mcp_relevance=[],
        claude_code_tips=[],
        caution=[],
        transcript_chars=0,
        was_skipped=True,
    )

    if isinstance(result, TranscriptSkip):
        return VideoResearchNote(**{**base, "skip_reason": f"transcript:{result.reason}"})

    text = result.full_text[:TRANSCRIPT_CHAR_CAP]
    try:
        response = llm.call(system=RESEARCH_SYSTEM_PROMPT, user=text, timeout_sec=120)
        raw = extract_fenced_json(response.text)
    except Exception as exc:
        log.warning("[LLM_FAIL] %s: %s", video.video_id, exc)
        return VideoResearchNote(**{**base, "transcript_chars": len(text), "skip_reason": f"llm_error:{type(exc).__name__}"})

    return parse_video_note(
        raw,
        video_id=video.video_id,
        title=video.title,
        url=video.url,
        published_date=published_date,
        transcript_chars=len(text),
    )
```

- [ ] **Step 4: Run analysis tests — all should pass**

```bash
cd /Users/kjun/vault/01_Projects/01_youtube_market_brief
uv run pytest tests/unit/test_claude_channel_research.py -k "analyze" -v
```

Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add scripts/claude_channel_research.py tests/unit/test_claude_channel_research.py
git commit -m "feat(research): add prompts and analyze_transcript wrapper"
```

---

## Task 4: Output File Writing

**Files:**
- Modify: `scripts/claude_channel_research.py` (add `write_note_file`, `write_synthesis_file`)
- Modify: `tests/unit/test_claude_channel_research.py`

- [ ] **Step 1: Add file writing tests**

Append to `tests/unit/test_claude_channel_research.py`:

```python
# ── write_note_file ───────────────────────────────────────────────────────────

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
        {"top_patterns": ["p1"], "quick_wins": [], "mcp_design_insights": [], "claude_code_insights": [], "longer_term": []},
        videos_analyzed=2,
        videos_skipped=0,
    )
    path = ccr.write_synthesis_file(report, tmp_path)

    assert path.exists()
    assert path.name.startswith("_synthesis_")
    assert path.name.endswith(".md")
    assert "p1" in path.read_text()
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd /Users/kjun/vault/01_Projects/01_youtube_market_brief
uv run pytest tests/unit/test_claude_channel_research.py -k "write" -v
```

Expected: `AttributeError: module 'claude_channel_research' has no attribute 'write_note_file'`

- [ ] **Step 3: Add file writing functions to the script**

Append to `scripts/claude_channel_research.py` (after `analyze_transcript`):

```python
# ── Output writing ────────────────────────────────────────────────────────────

def write_note_file(note: VideoResearchNote, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{note.published_date}_{note.video_id}.md"
    path.write_text(build_note_md(note), encoding="utf-8")
    return path


def write_synthesis_file(report: SynthesisReport, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"_synthesis_{report.generated_date}.md"
    path.write_text(build_synthesis_md(report), encoding="utf-8")
    return path
```

- [ ] **Step 4: Run file writing tests — all should pass**

```bash
cd /Users/kjun/vault/01_Projects/01_youtube_market_brief
uv run pytest tests/unit/test_claude_channel_research.py -k "write" -v
```

Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add scripts/claude_channel_research.py tests/unit/test_claude_channel_research.py
git commit -m "feat(research): add output file writing"
```

---

## Task 5: Orchestrator + CLI

**Files:**
- Modify: `scripts/claude_channel_research.py` (add `run_research`, `main`)
- Modify: `tests/unit/test_claude_channel_research.py`

- [ ] **Step 1: Add orchestrator tests**

Append to `tests/unit/test_claude_channel_research.py`:

```python
# ── run_research ──────────────────────────────────────────────────────────────

def _responder(note_json: str, synthesis_json: str):
    """Returns correct JSON depending on whether we're in synthesis or analysis call."""
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
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd /Users/kjun/vault/01_Projects/01_youtube_market_brief
uv run pytest tests/unit/test_claude_channel_research.py -k "run_research" -v
```

Expected: `AttributeError: module 'claude_channel_research' has no attribute 'run_research'`

- [ ] **Step 3: Add `run_research` and `main` to the script**

Append to `scripts/claude_channel_research.py`:

```python
# ── Orchestrator ──────────────────────────────────────────────────────────────

def run_research(
    *,
    channel_handle: str,
    published_after: datetime,
    max_videos: int,
    output_dir: Path,
    yt_client,
    transcript_client,
    llm_client,
) -> SynthesisReport:
    channel_id = yt_client.resolve_channel_id(channel_handle)
    if channel_id is None:
        raise ValueError(f"Could not resolve channel_id for handle: {channel_handle}")

    videos = yt_client.list_recent_videos(
        channel_id, published_after=published_after, max_results=max_videos
    )
    log.info("Discovered %d videos from %s", len(videos), channel_handle)

    notes: list[VideoResearchNote] = []
    for video in videos:
        result = transcript_client.fetch(video.video_id)
        note = analyze_transcript(video, result, llm_client)
        path = write_note_file(note, output_dir)
        log.info("[%s] %s → %s", "SKIP" if note.was_skipped else "OK", video.video_id, path)
        notes.append(note)

    processed = [n for n in notes if not n.was_skipped]
    skipped_count = len(notes) - len(processed)

    if not processed:
        log.warning("No videos processed — synthesis will be empty")
        raw_synthesis: dict = {}
    else:
        notes_json = json.dumps(
            [asdict(n) for n in processed], ensure_ascii=False, default=str
        )
        try:
            resp = llm_client.call(
                system=SYNTHESIS_SYSTEM_PROMPT, user=notes_json, timeout_sec=180
            )
            raw_synthesis = extract_fenced_json(resp.text)
        except Exception as exc:
            log.error("Synthesis LLM call failed: %s", exc)
            raw_synthesis = {}

    report = parse_synthesis(
        raw_synthesis, videos_analyzed=len(processed), videos_skipped=skipped_count
    )
    write_synthesis_file(report, output_dir)
    return report


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Research agent insights from @claude YouTube channel"
    )
    parser.add_argument("--handle", default="@claude")
    parser.add_argument("--months-back", type=int, default=6)
    parser.add_argument("--max-videos", type=int, default=50)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path.home() / "vault" / "00_Wiki" / "research" / "claude_channel",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    api_key = os.environ.get("YOUTUBE_API_KEY", "")
    if not api_key:
        print("ERROR: YOUTUBE_API_KEY env var required", file=sys.stderr)
        sys.exit(1)

    published_after = datetime.now(tz=UTC) - timedelta(days=args.months_back * 30)

    report = run_research(
        channel_handle=args.handle,
        published_after=published_after,
        max_videos=args.max_videos,
        output_dir=args.output_dir,
        yt_client=GoogleAPIYouTubeDataClient(api_key=api_key),
        transcript_client=YouTubeTranscriptApiClient(),
        llm_client=ClaudeCLIClient(),
    )

    print(f"\nDone. Analyzed: {report.videos_analyzed}, Skipped: {report.videos_skipped}")
    print(f"Synthesis: {args.output_dir / f'_synthesis_{report.generated_date}.md'}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run all tests — full suite should be green**

```bash
cd /Users/kjun/vault/01_Projects/01_youtube_market_brief
uv run pytest tests/unit/test_claude_channel_research.py -v
```

Expected: `13 passed` (3 parse + 3 build + 4 analyze + 3 write + 3 run_research)

- [ ] **Step 5: Run the full existing test suite to check for regressions**

```bash
cd /Users/kjun/vault/01_Projects/01_youtube_market_brief
uv run pytest tests/unit/ -v
```

Expected: All existing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add scripts/claude_channel_research.py tests/unit/test_claude_channel_research.py
git commit -m "feat(research): add run_research orchestrator and CLI — script complete"
```

---

## Task 6: Smoke Test (Live Run)

- [ ] **Step 1: Verify YOUTUBE_API_KEY is set**

```bash
echo $YOUTUBE_API_KEY | head -c 8
```

Expected: Shows first 8 chars of the key (non-empty). If empty, export it:
```bash
export YOUTUBE_API_KEY="$(grep YOUTUBE_API_KEY /Users/kjun/vault/01_Projects/01_youtube_market_brief/.env | cut -d= -f2)"
```

- [ ] **Step 2: Dry-run channel resolution only (manual check)**

```bash
cd /Users/kjun/vault/01_Projects/01_youtube_market_brief
uv run python -c "
import os
from youtube_market_brief._clients.youtube_data import GoogleAPIYouTubeDataClient
client = GoogleAPIYouTubeDataClient(os.environ['YOUTUBE_API_KEY'])
cid = client.resolve_channel_id('@claude')
print('channel_id:', cid)
"
```

Expected: Prints a `UC...` channel ID (not None).

- [ ] **Step 3: Run the script with `--max-videos 3` for a quick smoke test**

```bash
cd /Users/kjun/vault/01_Projects/01_youtube_market_brief
uv run python scripts/claude_channel_research.py --max-videos 3 --months-back 1
```

Expected:
- Logs `Discovered N videos`
- Per-video `[OK]` or `[SKIP]` lines
- Final `Done. Analyzed: X, Skipped: Y`
- Files created in `~/vault/00_Wiki/research/claude_channel/`

- [ ] **Step 4: Full run (all 6 months, up to 50 videos)**

```bash
cd /Users/kjun/vault/01_Projects/01_youtube_market_brief
uv run python scripts/claude_channel_research.py
```

Expected: `_synthesis_2026-05-11.md` in `~/vault/00_Wiki/research/claude_channel/`

---

## Self-Review Notes

**Spec coverage:**
- ✅ Reuses `_clients/{youtube_data,transcript,llm}.py` — no duplication
- ✅ `TRANSCRIPT_CHAR_CAP = 12_000` prevents context overflow
- ✅ `TranscriptSkip` → skip + continue
- ✅ `LLMCallError` → skip + continue
- ✅ Channel handle unresolvable → `ValueError` abort
- ✅ Per-video MD + synthesis MD output
- ✅ Frontmatter: `source_url, source_type, captured_at, channel, video_id, tags`
- ✅ `--max-videos 50` default, configurable via CLI
- ✅ `YOUTUBE_API_KEY` from env, clear error if missing

**Type consistency:**
- `parse_video_note` → `VideoResearchNote` ✅
- `parse_synthesis` → `SynthesisReport` ✅  
- `analyze_transcript` uses `parse_video_note` internally ✅
- `run_research` uses `analyze_transcript` + `write_note_file` + `write_synthesis_file` ✅
- `asdict(n)` in synthesis call — works on `@dataclass` but `AgentPattern` is nested; `asdict` handles nested dataclasses recursively ✅
