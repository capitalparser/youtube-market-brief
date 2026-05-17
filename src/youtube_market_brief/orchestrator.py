"""Pipeline orchestrator: assembles stages with failure isolation + RunReport."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from youtube_market_brief._clients.llm import LLMClient
from youtube_market_brief._clients.telegram import TelegramClient
from youtube_market_brief._clients.transcript import TranscriptClient
from youtube_market_brief._clients.youtube_data import YouTubeDataClient
from youtube_market_brief.config import (
    AppConfig,
    load_channels,
    load_watchlist,
    persist_resolved_channel_id,
)
from youtube_market_brief.domain.types import (
    RunFailure,
    RunReport,
    TranscriptSkip,
    VideoAnalysis,
)
from youtube_market_brief.pipeline import (
    aggregate as agg,
)
from youtube_market_brief.pipeline import (
    discover as discover_mod,
)
from youtube_market_brief.pipeline import (
    propagation as propagation_mod,
)
from youtube_market_brief.pipeline import (
    video_processing as video_processing_mod,
)
from youtube_market_brief.state.store import IdempotencyStore

log = logging.getLogger(__name__)


@dataclass
class Clients:
    youtube: YouTubeDataClient
    transcript: TranscriptClient
    llm: LLMClient
    telegram: TelegramClient


def run(
    *,
    config: AppConfig,
    clients: Clients,
    target_date: date | None = None,
    force: bool = False,
    send_daily_brief: bool = True,
) -> RunReport:
    started = time.monotonic()
    now_local = datetime.now(tz=config.tz)
    if target_date is None:
        target_date = now_local.date()
    published_after = datetime.combine(
        target_date, datetime.min.time(), tzinfo=config.tz
    ) - timedelta(hours=24)
    published_before = datetime.combine(
        target_date + timedelta(days=1), datetime.min.time(), tzinfo=config.tz
    )

    report = RunReport(date=target_date)

    channels = load_channels(config.channels_path)
    watchlist = load_watchlist(config.watchlist_path)
    if not channels:
        log.warning("no channels configured at %s — nothing to do", config.channels_path)
        report.duration_sec = time.monotonic() - started
        return report

    if watchlist.is_empty():
        log.warning("watchlist empty at %s — auto-discovery only", config.watchlist_path)

    store = IdempotencyStore(config.state_path)

    # Discover
    def _on_resolved(slug: str, cid: str) -> None:
        persist_resolved_channel_id(config.channels_path, slug, cid)

    videos = discover_mod.discover_new_videos(
        channels=channels,
        yt=clients.youtube,
        store=store,
        published_after=published_after,
        published_before=published_before,
        skip_shorts=config.skip_shorts,
        on_resolved_channel=_on_resolved,
    )
    report.discovered = len(videos)
    log.info("discovered %d new video(s) for %s", len(videos), target_date.isoformat())

    if config.max_videos_per_run and len(videos) > config.max_videos_per_run:
        log.warning(
            "discovered %d > max_videos_per_run %d — processing first %d, rest carried to next run",
            len(videos),
            config.max_videos_per_run,
            config.max_videos_per_run,
        )
        videos = videos[: config.max_videos_per_run]

    analyses: list[VideoAnalysis] = []
    captured_at = datetime.now(tz=config.tz)
    date_kst_iso = target_date.isoformat()
    system_prompt_path = config.prompts_dir / "system_video_analysis.ko.md"

    # Per-video pipeline
    for v in videos:
        try:
            result = video_processing_mod.process_video(
                video=v,
                transcript_client=clients.transcript,
                watchlist=watchlist,
                llm=clients.llm,
                telegram=clients.telegram,
                store=store,
                vault_root=config.vault_root,
                vault_youtube_root=config.vault_youtube_root,
                system_prompt_path=system_prompt_path,
                captured_at=captured_at,
                date_kst_iso=date_kst_iso,
                transcript_max_chars=config.transcript_max_chars,
                timeout_sec=config.claude_timeout_sec,
                notify=True,
            )
            if isinstance(result.skip, TranscriptSkip):
                log.info("skip %s: %s (%s)", v.video_id, result.skip.reason, result.skip.detail)
                report.skipped_no_caption += 1
                continue
            if result.analysis is not None:
                analyses.append(result.analysis)
            report.processed += 1
        except Exception as e:
            log.error("per-video pipeline failed for %s: %s", v.video_id, e, exc_info=True)
            report.failed.append(
                RunFailure(video_id=v.video_id, error_class=type(e).__name__, message=str(e))
            )
            try:
                store.mark_video(
                    v.video_id,
                    channel_id=v.channel_id,
                    outcome="failed",
                    md_path=None,
                    processed_at=captured_at,
                )
                store.flush()
            except Exception:
                log.exception("failed to record failure state for %s", v.video_id)

    # Daily brief
    if analyses and send_daily_brief and (force or not store.daily_brief_sent(target_date)):
        try:
            brief = agg.aggregate_daily(
                analyses=analyses,
                target_date=target_date,
                llm=clients.llm,
                system_prompt_path=config.prompts_dir / "system_daily_brief.ko.md",
                timeout_sec=config.claude_timeout_sec,
            )
            if brief is not None:
                brief_path = agg.write_daily_brief_md(
                    brief,
                    vault_daily_root=config.vault_daily_root,
                    captured_at=captured_at,
                )
                report.daily_brief_generated = True
                sidecar_path = brief_path.with_suffix(".analysis.json")
                propagation_result = propagation_mod.create_daily_propagation_proposal(
                    sidecar_path=sidecar_path,
                    vault_root=config.vault_root,
                )
                if propagation_result.ok:
                    log.info(
                        "daily propagation proposal generated: %s",
                        propagation_result.proposal_path,
                    )
                elif not propagation_result.skipped:
                    log.warning(
                        "daily propagation proposal failed: %s",
                        propagation_result.message,
                    )
                res = notify_mod.notify_daily(brief, telegram=clients.telegram)
                report.daily_brief_sent = res.ok
                store.mark_daily_brief(
                    target_date,
                    brief_sent=res.ok,
                    brief_path=brief_path.relative_to(config.vault_root).as_posix(),
                )
                store.flush()
        except Exception as e:
            log.error("daily brief stage failed: %s", e, exc_info=True)

    store.set_last_run(captured_at)
    store.flush()
    report.duration_sec = time.monotonic() - started
    log.info(
        "run summary date=%s discovered=%d processed=%d skipped=%d failed=%d duration=%.1fs",
        target_date.isoformat(),
        report.discovered,
        report.processed,
        report.skipped_no_caption,
        len(report.failed),
        report.duration_sec,
    )
    return report
