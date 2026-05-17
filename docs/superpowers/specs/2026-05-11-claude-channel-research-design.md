# Design: Claude Channel Agent Research Script

**Date:** 2026-05-11  
**Type:** One-off research tool  
**Location:** `scripts/claude_channel_research.py`  
**Project:** `01_youtube_market_brief`

---

## Goal

Extract agent development insights from the Anthropic @claude YouTube channel (last 6 months). Focus areas: PAS system enhancement, MCP server design, Claude Code collaboration flow. Output: per-video vault notes + synthesis report.

---

## Architecture

```
scripts/claude_channel_research.py
        │
        ├── GoogleAPIYouTubeDataClient.list_recent_videos(
        │       channel_id (resolved from @claude handle),
        │       published_after=2025-11-11,
        │       max_results=50
        │   )  → list[VideoMeta]
        │
        ├── for each video:
        │     YouTubeTranscriptApiClient.fetch(video_id)
        │           → Transcript | TranscriptSkip
        │     (TranscriptSkip → log + continue)
        │
        │     ClaudeCLIClient.call(
        │         system=RESEARCH_SYSTEM_PROMPT,
        │         user=transcript.full_text[:12000]  # char cap
        │     )  → VideoResearchNote (JSON)
        │
        │     write_video_note(note) →
        │         00_Wiki/research/claude_channel/{YYYY-MM-DD}_{video_id}.md
        │
        └── ClaudeCLIClient.call(
                system=SYNTHESIS_SYSTEM_PROMPT,
                user=json.dumps([note.__dict__ for note in notes], ensure_ascii=False)
            )  → SynthesisReport (JSON)
            write → 00_Wiki/research/claude_channel/_synthesis_2026-05-11.md
```

---

## Data Models

### VideoResearchNote

```python
@dataclass
class VideoResearchNote:
    video_id: str
    title: str
    url: str
    published_date: str          # YYYY-MM-DD
    summary: str                 # one-line
    key_insights: list[str]      # 3-5 items
    agent_patterns: list[AgentPattern]
    api_techniques: list[str]    # Claude API specific techniques
    mcp_relevance: list[str]     # direct MCP design applicability
    claude_code_tips: list[str]  # Claude Code workflow improvements
    caution: list[str]           # pitfalls / things to avoid
    transcript_chars: int
    was_skipped: bool = False
    skip_reason: str = ""

@dataclass
class AgentPattern:
    pattern: str          # pattern name
    description: str      # what it is
    applicability: str    # how it applies to our PAS/MCP/Claude Code work
```

### SynthesisReport

```python
@dataclass
class SynthesisReport:
    generated_date: str
    videos_analyzed: int
    videos_skipped: int
    top_patterns: list[str]          # patterns repeated across videos
    quick_wins: list[str]            # immediately actionable
    mcp_design_insights: list[str]   # MCP server design takeaways
    claude_code_insights: list[str]  # Claude Code flow improvements
    longer_term: list[str]           # items requiring deeper work
```

---

## Prompts

### RESEARCH_SYSTEM_PROMPT

Context: analyzing a transcript from the Anthropic @claude YouTube channel.  
Task: extract agent development insights relevant to:
1. Personal agent system (PAS) — Runner/Trigger/Sink architecture improvements
2. MCP server design patterns
3. Claude Code collaboration workflows

Output: fenced JSON block matching `VideoResearchNote` schema (minus `video_id/title/url/published_date`).  
If the video is not relevant to agent development (e.g., brand ads, unrelated content), return empty arrays.

### SYNTHESIS_SYSTEM_PROMPT

Context: a collection of `VideoResearchNote` objects from Claude channel.  
Task: synthesize cross-video patterns into a `SynthesisReport`.  
Prioritize items that appear in 2+ videos. Separate quick wins (apply this week) from longer-term patterns.

---

## Output Files

| Path | Content |
|------|---------|
| `00_Wiki/research/claude_channel/{YYYY-MM-DD}_{video_id}.md` | Per-video frontmatter + note |
| `00_Wiki/research/claude_channel/_synthesis_2026-05-11.md` | Final synthesis report |

### Per-video MD frontmatter

```yaml
---
source_url: https://youtu.be/{video_id}
source_type: youtube
captured_at: 2026-05-11
channel: claude_official
video_id: {video_id}
tags: [agent-research, claude-channel]
---
```

---

## Configuration

| Parameter | Value |
|-----------|-------|
| `PUBLISHED_AFTER` | 2025-11-11 (6 months ago) |
| `MAX_VIDEOS` | 50 |
| `TRANSCRIPT_CHAR_CAP` | 12,000 chars (prevent context overflow) |
| `LLM_TIMEOUT_SEC` | 120 |
| `CHANNEL_HANDLE` | `@claude` |
| `OUTPUT_DIR` | `~/vault/00_Wiki/research/claude_channel/` |

---

## Reuse vs New

| Component | Source |
|-----------|--------|
| `GoogleAPIYouTubeDataClient` | `_clients/youtube_data.py` — import as-is |
| `YouTubeTranscriptApiClient` | `_clients/transcript.py` — import as-is |
| `ClaudeCLIClient`, `extract_fenced_json` | `_clients/llm.py` — import as-is |
| `VideoMeta`, `Transcript`, `TranscriptSkip` | `domain/types.py` — import as-is |
| `VideoResearchNote`, `AgentPattern`, `SynthesisReport` | New — inline in script |
| `RESEARCH_SYSTEM_PROMPT`, `SYNTHESIS_SYSTEM_PROMPT` | New — inline in script |

---

## Error Handling

- `TranscriptSkip` → log `[SKIP] {video_id}: {reason}`, continue
- `LLMCallError` → log `[LLM_FAIL] {video_id}`, mark `was_skipped=True`, continue
- JSON parse failure → log warning, skip from synthesis
- Channel resolve failure (`resolve_channel_id` returns None) → abort with clear message

---

## Out of Scope

- Recurring / scheduled runs (one-off only)
- Telegram notification
- Idempotency store
- Korean transcript preference (Claude channel is primarily English)
