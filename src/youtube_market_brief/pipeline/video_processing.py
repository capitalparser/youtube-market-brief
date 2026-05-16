"""Shared per-video processing pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from youtube_market_brief._clients.llm import LLMClient
from youtube_market_brief._clients.telegram import TelegramClient
from youtube_market_brief._clients.transcript import TranscriptClient
from youtube_market_brief.domain.types import TranscriptSkip, VideoAnalysis, VideoMeta, Watchlist
from youtube_market_brief.pipeline.analyze import analyze_video
from youtube_market_brief.pipeline.notify import notify_per_video
from youtube_market_brief.pipeline.transcribe import fetch_transcript
from youtube_market_brief.pipeline.write_video import write_video_md
from youtube_market_brief.state.store import IdempotencyStore


@dataclass(frozen=True)
class VideoProcessResult:
    video_id: str
    analysis: VideoAnalysis | None = None
    md_relative: str | None = None
    skip: TranscriptSkip | None = None


def process_video(
    *,
    video: VideoMeta,
    transcript_client: TranscriptClient,
    watchlist: Watchlist,
    llm: LLMClient,
    telegram: TelegramClient,
    store: IdempotencyStore,
    vault_root: Path,
    vault_youtube_root: Path,
    system_prompt_path: Path,
    captured_at: datetime,
    date_kst_iso: str,
    transcript_max_chars: int,
    timeout_sec: int,
    notify: bool = True,
) -> VideoProcessResult:
    """Process one video and checkpoint idempotency state.

    Exceptions intentionally bubble to the caller so run-level orchestrators can
    decide how to report and isolate failures.
    """
    transcript = fetch_transcript(
        video,
        client=transcript_client,
        max_chars=transcript_max_chars,
    )
    if isinstance(transcript, TranscriptSkip):
        store.mark_video(
            video.video_id,
            channel_id=video.channel_id,
            outcome="skipped_no_caption",
            md_path=None,
            processed_at=captured_at,
            skip_reason=transcript.reason,
        )
        store.flush()
        return VideoProcessResult(video_id=video.video_id, skip=transcript)

    analysis = analyze_video(
        video=video,
        transcript=transcript,
        watchlist=watchlist,
        llm=llm,
        system_prompt_path=system_prompt_path,
        timeout_sec=timeout_sec,
    )
    md_path = write_video_md(
        analysis,
        vault_youtube_root=vault_youtube_root,
        captured_at=captured_at,
        date_kst_iso=date_kst_iso,
    )
    md_relative = md_path.relative_to(vault_root).as_posix()
    if notify:
        notify_per_video(
            analysis,
            telegram=telegram,
            vault_md_path_relative=md_relative,
        )
    store.mark_video(
        video.video_id,
        channel_id=video.channel_id,
        outcome="ok",
        md_path=md_relative,
        processed_at=captured_at,
    )
    store.flush()
    return VideoProcessResult(
        video_id=video.video_id,
        analysis=analysis,
        md_relative=md_relative,
    )
