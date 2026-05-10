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
    analyze as analyze_mod,
)
from youtube_market_brief.pipeline import (
    discover as discover_mod,
)
from youtube_market_brief.pipeline import (
    notify as notify_mod,
)
from youtube_market_brief.pipeline import (
    transcribe as transcribe_mod,
)
from youtube_market_brief.pipeline import (
    write_video as write_mod,
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
            tx = transcribe_mod.fetch_transcript(
                v, client=clients.transcript, max_chars=config.transcript_max_chars
            )
            if isinstance(tx, TranscriptSkip):
                log.info("skip %s: %s (%s)", v.video_id, tx.reason, tx.detail)
                report.skipped_no_caption += 1
                store.mark_video(
                    v.video_id,
                    channel_id=v.channel_id,
                    outcome="skipped_no_caption",
                    md_path=None,
                    processed_at=captured_at,
                )
                continue

            analysis = analyze_mod.analyze_video(
                video=v,
                transcript=tx,
                watchlist=watchlist,
                llm=clients.llm,
                system_prompt_path=system_prompt_path,
                timeout_sec=config.claude_timeout_sec,
            )
            md_path = write_mod.write_video_md(
                analysis,
                vault_youtube_root=config.vault_youtube_root,
                captured_at=captured_at,
                date_kst_iso=date_kst_iso,
            )

            md_relative = md_path.relative_to(config.vault_root).as_posix()
            res = notify_mod.notify_per_video(
                analysis, telegram=clients.telegram, vault_md_path_relative=md_relative
            )
            if not res.ok:
                log.warning("per_video notify failed for %s: %s", v.video_id, res.error)

            store.mark_video(
                v.video_id,
                channel_id=v.channel_id,
                outcome="ok",
                md_path=md_relative,
                processed_at=captured_at,
            )
            store.flush()  # checkpoint after each video
            analyses.append(analysis)
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
