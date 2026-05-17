#!/usr/bin/env python3
"""One-off research script: agent insights from the @claude YouTube channel.

Fetches recent videos, transcribes via youtube-transcript-api, analyzes each
with Claude using a custom agent-research prompt, then synthesizes the results.

Outputs:
- Per-video notes: {output_dir}/{YYYY-MM-DD}_{video_id}.md
- Synthesis report: {output_dir}/_synthesis_{YYYY-MM-DD}.md

Usage:
    YOUTUBE_API_KEY=... uv run python scripts/claude_channel_research.py
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

from youtube_market_brief._clients.llm import (
    ClaudeCLIClient,
    extract_fenced_json,
)

load_dotenv()
from youtube_market_brief._clients.transcript import (
    YouTubeTranscriptApiClient,
    YtDlpTranscriptClient,
)
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
    ]
    if note.summary:
        lines += [f"> {note.summary}", ""]

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
            lines += [
                f"### {p.pattern}",
                p.description,
                "",
                f"**Applicability:** {p.applicability}",
                "",
            ]

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
If the video is not relevant to agent development (brand ads, unrelated content), return empty arrays for all list fields.
Be specific and actionable. No generic advice."""

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

    def _skipped(reason: str, transcript_chars: int = 0) -> VideoResearchNote:
        return VideoResearchNote(
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
            transcript_chars=transcript_chars,
            was_skipped=True,
            skip_reason=reason,
        )

    if isinstance(result, TranscriptSkip):
        return _skipped(f"transcript:{result.reason}")

    text = result.full_text[:TRANSCRIPT_CHAR_CAP]
    try:
        response = llm.call(system=RESEARCH_SYSTEM_PROMPT, user=text, timeout_sec=120)
        raw = extract_fenced_json(response.text)
    except Exception as exc:
        log.warning("[LLM_FAIL] %s: %s", video.video_id, exc)
        return _skipped(f"llm_error:{type(exc).__name__}", transcript_chars=len(text))

    if not isinstance(raw, dict):
        log.warning("[LLM_PARSE] %s: expected dict, got %s", video.video_id, type(raw).__name__)
        return _skipped("llm_error:NotDict", transcript_chars=len(text))

    return parse_video_note(
        raw,
        video_id=video.video_id,
        title=video.title,
        url=video.url,
        published_date=published_date,
        transcript_chars=len(text),
    )


# ── Output writing ────────────────────────────────────────────────────────────

def write_note_file(note: VideoResearchNote, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{note.published_date}_{note.video_id}.md"
    path.write_text(build_note_md(note), encoding="utf-8")
    json_path = path.with_suffix(".json")
    json_path.write_text(
        json.dumps(asdict(note), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return path


def write_synthesis_file(report: SynthesisReport, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"_synthesis_{report.generated_date}.md"
    path.write_text(build_synthesis_md(report), encoding="utf-8")
    return path


# ── Transcript fallback chain ─────────────────────────────────────────────────

class FallbackTranscriptClient:
    """Try `primary`; on `ip_blocked` skip, fall back to `secondary`."""

    def __init__(self, primary, secondary):
        self._primary = primary
        self._secondary = secondary

    def fetch(self, video_id: str) -> Transcript | TranscriptSkip:
        result = self._primary.fetch(video_id)
        if isinstance(result, TranscriptSkip) and result.reason == "ip_blocked":
            log.info("primary transcript ip_blocked, retrying with fallback for %s", video_id)
            return self._secondary.fetch(video_id)
        return result


# ── Idempotency ───────────────────────────────────────────────────────────────

def _existing_note_path(video_id: str, published_date: str, output_dir: Path) -> Path:
    return output_dir / f"{published_date}_{video_id}.md"


def _is_recoverable_skip(content: str) -> bool:
    """Skip files we should retry on subsequent runs."""
    return any(
        marker in content
        for marker in (
            "Skipped: transcript:ip_blocked",
            "Skipped: transcript:api_changed",
            "Skipped: transcript:timeout",
            "Skipped: llm_error",
        )
    )


def load_existing_note(video: VideoMeta, output_dir: Path) -> VideoResearchNote | None:
    """Return parsed note from sidecar JSON if file exists and is not recoverable-skip;
    None if missing or recoverable-skip."""
    published_date = video.published_at_utc.strftime("%Y-%m-%d")
    md_path = _existing_note_path(video.video_id, published_date, output_dir)
    json_path = md_path.with_suffix(".json")
    if not md_path.exists():
        return None
    md_content = md_path.read_text(encoding="utf-8")
    if _is_recoverable_skip(md_content):
        return None
    if not json_path.exists():
        return None
    raw = json.loads(json_path.read_text(encoding="utf-8"))
    patterns = [AgentPattern(**p) for p in raw.get("agent_patterns", [])]
    return VideoResearchNote(
        video_id=raw["video_id"],
        title=raw["title"],
        url=raw["url"],
        published_date=raw["published_date"],
        summary=raw.get("summary", ""),
        key_insights=list(raw.get("key_insights", [])),
        agent_patterns=patterns,
        api_techniques=list(raw.get("api_techniques", [])),
        mcp_relevance=list(raw.get("mcp_relevance", [])),
        claude_code_tips=list(raw.get("claude_code_tips", [])),
        caution=list(raw.get("caution", [])),
        transcript_chars=raw.get("transcript_chars", 0),
        was_skipped=raw.get("was_skipped", False),
        skip_reason=raw.get("skip_reason", ""),
    )


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
    skip_existing: bool = True,
    request_delay_sec: float = 0.0,
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
        cached = load_existing_note(video, output_dir) if skip_existing else None
        if cached is not None:
            log.info(
                "[CACHE] %s → %s",
                video.video_id,
                _existing_note_path(video.video_id, cached.published_date, output_dir),
            )
            notes.append(cached)
            continue

        if request_delay_sec > 0:
            time.sleep(request_delay_sec)
        result = transcript_client.fetch(video.video_id)
        note = analyze_transcript(video, result, llm_client)
        path = write_note_file(note, output_dir)
        log.info(
            "[%s] %s → %s",
            "SKIP" if note.was_skipped else "OK",
            video.video_id,
            path,
        )
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
            if not isinstance(raw_synthesis, dict):
                log.warning("Synthesis returned non-dict — using empty report")
                raw_synthesis = {}
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
    parser.add_argument(
        "--no-fallback",
        action="store_true",
        help="Disable yt-dlp fallback for ip_blocked transcripts",
    )
    parser.add_argument(
        "--request-delay",
        type=float,
        default=3.0,
        help="Delay between transcript requests in seconds (default: 3.0)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    api_key = os.environ.get("YOUTUBE_API_KEY", "")
    if not api_key:
        print("ERROR: YOUTUBE_API_KEY env var required", file=sys.stderr)
        sys.exit(1)

    published_after = datetime.now(tz=UTC) - timedelta(days=args.months_back * 30)

    cookie_file = os.environ.get("YOUTUBE_COOKIE_FILE", "") or None
    primary = YouTubeTranscriptApiClient(cookie_file=cookie_file)
    transcript_client = (
        primary
        if args.no_fallback
        else FallbackTranscriptClient(primary, YtDlpTranscriptClient(cookie_file=cookie_file))
    )

    report = run_research(
        channel_handle=args.handle,
        published_after=published_after,
        max_videos=args.max_videos,
        output_dir=args.output_dir,
        yt_client=GoogleAPIYouTubeDataClient(api_key=api_key),
        transcript_client=transcript_client,
        llm_client=ClaudeCLIClient(),
        request_delay_sec=args.request_delay,
    )

    print(f"\nDone. Analyzed: {report.videos_analyzed}, Skipped: {report.videos_skipped}")
    print(
        f"Synthesis: {args.output_dir / f'_synthesis_{report.generated_date}.md'}"
    )


if __name__ == "__main__":
    main()
