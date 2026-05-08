"""CLI entrypoint: ymb {health,run,discover,analyze}."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import UTC, date

from youtube_market_brief import __version__
from youtube_market_brief.config import load_app_config
from youtube_market_brief.logging_setup import setup_logging

log = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ymb",
        description="YouTube Market Brief — daily ingestion + 시장 분석 + Telegram",
    )
    parser.add_argument("--version", action="version", version=f"ymb {__version__}")
    sub = parser.add_subparsers(dest="cmd")

    p_health = sub.add_parser("health", help="Verify claude CLI auth and basic config")
    p_health.set_defaults(func=cmd_health)

    p_config = sub.add_parser("config", help="Config inspection")
    p_config.add_argument("action", choices=["show", "validate"], default="show", nargs="?")
    p_config.set_defaults(func=cmd_config)

    p_run = sub.add_parser("run", help="Execute daily pipeline")
    p_run.add_argument("--date", type=_parse_date, default=None, help="Target date YYYY-MM-DD (KST). Default: today")
    p_run.add_argument("--dry-run", action="store_true", help="Override DRY_RUN=true (Telegram → file dump)")
    p_run.add_argument("--force", action="store_true", help="Re-process and re-send daily brief even if already done")
    p_run.set_defaults(func=cmd_run)

    p_discover = sub.add_parser("discover", help="(Phase 1) discovery smoke test")
    p_discover.add_argument("--channel-id", type=str, default=None)
    p_discover.add_argument("--handle", type=str, default=None)
    p_discover.add_argument("--since", type=_parse_date, default=None)
    p_discover.set_defaults(func=cmd_discover)

    p_analyze = sub.add_parser("analyze", help="(Phase 2) analyze a fixture transcript JSON")
    p_analyze.add_argument("--transcript-fixture", type=str, required=True)
    p_analyze.set_defaults(func=cmd_analyze)

    p_agg = sub.add_parser(
        "aggregate-only",
        help="Rebuild daily brief from existing vault MDs (no video reprocessing)",
    )
    p_agg.add_argument("--date", type=_parse_date, required=True, help="Target date YYYY-MM-DD")
    p_agg.add_argument("--no-telegram", action="store_true", help="Skip Telegram delivery")
    p_agg.add_argument(
        "--full-body",
        action="store_true",
        help="Send full MD bodies to LLM (default: extract key sections only)",
    )
    p_agg.set_defaults(func=cmd_aggregate_only)

    args = parser.parse_args(argv)
    if not getattr(args, "cmd", None):
        parser.print_help()
        return 0
    return args.func(args)


def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


def _make_llm_client(cfg):
    """Construct the LLM client based on LLM_PROVIDER config.

    api → AnthropicAPIClient (Anthropic Messages API). Default. Cloud-runnable.
    cli → ClaudeCLIClient   (subprocess to `claude` CLI). Local-only.
    """
    from youtube_market_brief._clients.llm import (
        AnthropicAPIClient,
        ClaudeCLIClient,
    )

    if cfg.llm_provider == "cli":
        return ClaudeCLIClient(bin_path=cfg.claude_bin, model=cfg.claude_model)
    if cfg.llm_provider != "api":
        log.warning(
            "unknown LLM_PROVIDER=%s — falling back to api", cfg.llm_provider
        )
    return AnthropicAPIClient(
        api_key=cfg.anthropic_api_key or None,
        model=cfg.anthropic_model,
    )


def cmd_health(args) -> int:
    cfg = load_app_config()
    setup_logging(level=cfg.log_level, logs_dir=cfg.logs_dir, tz=cfg.tz)

    log.info("project_root=%s vault_root=%s", cfg.project_root, cfg.vault_root)
    log.info("llm_provider=%s", cfg.llm_provider)
    if cfg.llm_provider == "cli":
        log.info("claude_bin=%s claude_model=%s", cfg.claude_bin, cfg.claude_model)
    else:
        log.info("anthropic_model=%s key_set=%s", cfg.anthropic_model, bool(cfg.anthropic_api_key))
    client = _make_llm_client(cfg)
    ok = client.health_check()
    if ok:
        print(f"OK: LLM client responded (provider={cfg.llm_provider}).")
        return 0
    print(
        f"FAIL: LLM client did not respond (provider={cfg.llm_provider}). "
        f"Check credentials and connectivity.",
        file=sys.stderr,
    )
    return 2


def cmd_config(args) -> int:
    cfg = load_app_config()
    info = {
        "project_root": str(cfg.project_root),
        "vault_root": str(cfg.vault_root),
        "vault_youtube_root": str(cfg.vault_youtube_root),
        "state_path": str(cfg.state_path),
        "llm_provider": cfg.llm_provider,
        "anthropic_model": cfg.anthropic_model,
        "anthropic_api_key_set": bool(cfg.anthropic_api_key),
        "claude_bin": cfg.claude_bin,
        "claude_model": cfg.claude_model,
        "timezone": cfg.timezone,
        "max_videos_per_run": cfg.max_videos_per_run,
        "transcript_max_chars": cfg.transcript_max_chars,
        "skip_shorts": cfg.skip_shorts,
        "dry_run": cfg.dry_run,
        "channels_path_exists": cfg.channels_path.exists(),
        "watchlist_path_exists": cfg.watchlist_path.exists(),
        "youtube_api_key_set": bool(cfg.youtube_api_key),
        "telegram_set": bool(cfg.telegram_bot_token and cfg.telegram_chat_id),
    }
    print(json.dumps(info, ensure_ascii=False, indent=2))
    if args.action == "validate":
        missing = []
        if not cfg.youtube_api_key:
            missing.append("YOUTUBE_API_KEY")
        if not cfg.telegram_bot_token:
            missing.append("TELEGRAM_BOT_TOKEN")
        if not cfg.telegram_chat_id:
            missing.append("TELEGRAM_CHAT_ID")
        if not cfg.channels_path.exists():
            missing.append("config/channels.yaml")
        if missing:
            print(f"\nMISSING: {', '.join(missing)}", file=sys.stderr)
            return 2
        print("\nOK: required env + config present.")
    return 0


def cmd_run(args) -> int:
    cfg = load_app_config()
    setup_logging(level=cfg.log_level, logs_dir=cfg.logs_dir, tz=cfg.tz)
    from youtube_market_brief._clients.telegram import (
        DryRunTelegramClient,
        HttpxTelegramClient,
    )
    from youtube_market_brief._clients.transcript import YouTubeTranscriptApiClient
    from youtube_market_brief._clients.youtube_data import GoogleAPIYouTubeDataClient
    from youtube_market_brief.orchestrator import Clients, run

    if args.dry_run:
        # Override env for this invocation
        import os
        os.environ["DRY_RUN"] = "true"
        cfg.dry_run = True

    yt_client = GoogleAPIYouTubeDataClient(api_key=cfg.youtube_api_key)
    transcript_client = YouTubeTranscriptApiClient()
    llm_client = _make_llm_client(cfg)
    if cfg.dry_run or not (cfg.telegram_bot_token and cfg.telegram_chat_id):
        telegram_client = DryRunTelegramClient(cfg.telegram_dryrun_dir)
    else:
        telegram_client = HttpxTelegramClient(
            bot_token=cfg.telegram_bot_token, chat_id=cfg.telegram_chat_id
        )
    clients = Clients(
        youtube=yt_client,
        transcript=transcript_client,
        llm=llm_client,
        telegram=telegram_client,
    )
    report = run(
        config=cfg,
        clients=clients,
        target_date=args.date,
        force=args.force,
    )
    payload = {
        "date": report.date.isoformat(),
        "discovered": report.discovered,
        "processed": report.processed,
        "skipped_no_caption": report.skipped_no_caption,
        "skipped_idempotent": report.skipped_idempotent,
        "failed": [
            {"video_id": f.video_id, "error_class": f.error_class, "message": f.message}
            for f in report.failed
        ],
        "daily_brief_generated": report.daily_brief_generated,
        "daily_brief_sent": report.daily_brief_sent,
        "duration_sec": round(report.duration_sec, 2),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if not report.failed else 1


def cmd_discover(args) -> int:
    """(Phase 1) Smoke test discovery against a single channel."""
    cfg = load_app_config()
    setup_logging(level=cfg.log_level, logs_dir=cfg.logs_dir, tz=cfg.tz)
    from youtube_market_brief._clients.youtube_data import GoogleAPIYouTubeDataClient

    yt = GoogleAPIYouTubeDataClient(api_key=cfg.youtube_api_key)
    if args.handle:
        cid = yt.resolve_channel_id(args.handle)
        print(f"resolve {args.handle} → {cid}")
    elif args.channel_id:
        cid = args.channel_id
    else:
        print("provide --handle or --channel-id", file=sys.stderr)
        return 2
    if not cid:
        return 2
    from datetime import datetime, timedelta
    after = datetime.now(tz=cfg.tz) - timedelta(days=2)
    if args.since:
        from datetime import datetime as _dt
        after = _dt.combine(args.since, _dt.min.time(), tzinfo=cfg.tz)
    videos = yt.list_recent_videos(cid, published_after=after, max_results=10)
    out = [
        {
            "video_id": v.video_id,
            "title": v.title,
            "url": v.url,
            "published_at_utc": v.published_at_utc.isoformat(),
            "duration_sec": v.duration_sec,
        }
        for v in videos
    ]
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def cmd_analyze(args) -> int:
    """(Phase 2) Analyze a fixture transcript JSON file (no YouTube/Telegram)."""
    cfg = load_app_config()
    setup_logging(level=cfg.log_level, logs_dir=cfg.logs_dir, tz=cfg.tz)
    from youtube_market_brief.config import load_watchlist
    from youtube_market_brief.pipeline.analyze import analyze_video

    fixture_path = args.transcript_fixture
    fixture = json.loads(open(fixture_path, encoding="utf-8").read())
    video = _video_from_fixture(fixture)
    transcript = _transcript_from_fixture(fixture)
    watchlist = load_watchlist(cfg.watchlist_path)
    llm = _make_llm_client(cfg)
    result = analyze_video(
        video=video,
        transcript=transcript,
        watchlist=watchlist,
        llm=llm,
        system_prompt_path=cfg.prompts_dir / "system_video_analysis.ko.md",
        timeout_sec=cfg.claude_timeout_sec,
    )
    out = {
        "video_id": result.video.video_id,
        "tier": result.tier,
        "headline_3line": list(result.transcript_summary.headline_3line),
        "key_insights": list(result.transcript_summary.key_insights),
        "red_team": list(result.transcript_summary.red_team),
        "watchlist_hits": list(result.watchlist_hits),
        "tickers": [
            {
                "symbol": t.symbol,
                "display": t.display,
                "in_watchlist": t.in_watchlist,
                "direction": t.direction,
                "confidence": t.confidence,
                "reasoning": t.reasoning,
                "quotes": list(t.quotes),
            }
            for t in result.tickers
        ],
        "tags": list(result.tags),
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def cmd_aggregate_only(args) -> int:
    """Rebuild daily brief from existing per-video MDs in vault.

    No video reprocessing — reads MD files matching `{date}__*.md` under each
    channel folder, sends them as raw markdown context to the LLM along with
    the daily-brief system prompt, parses the structured response, writes the
    daily brief MD, and (optionally) sends to Telegram.
    """
    import re
    from datetime import datetime as _dt
    from pathlib import Path

    import yaml as yaml_mod

    cfg = load_app_config()
    setup_logging(level=cfg.log_level, logs_dir=cfg.logs_dir, tz=cfg.tz)

    from youtube_market_brief._clients.llm import extract_fenced_json
    from youtube_market_brief._clients.telegram import (
        DryRunTelegramClient,
        HttpxTelegramClient,
    )
    from youtube_market_brief.domain.types import (
        DailyBrief,
        LLMMeta,
        TickerRollup,
        TickerRollupVideoEntry,
        VideoMeta,
    )
    from youtube_market_brief.pipeline.aggregate import write_daily_brief_md
    from youtube_market_brief.pipeline.notify import notify_daily
    from youtube_market_brief.state.store import IdempotencyStore

    target_date = args.date
    pattern = f"{target_date.isoformat()}__*.md"
    md_paths = sorted(cfg.vault_youtube_root.glob(f"*/{pattern}"))
    md_paths = [p for p in md_paths if not p.parent.name.startswith("_")]
    if not md_paths:
        print(f"No vault MDs found for {target_date.isoformat()}", file=sys.stderr)
        return 1

    log.info("aggregate-only %s: found %d vault MD(s)", target_date.isoformat(), len(md_paths))

    fm_re = re.compile(r"^---\n(.+?)\n---\n(.*)$", re.DOTALL)
    title_re = re.compile(r"^# (.+)$", re.MULTILINE)
    meta_re = re.compile(r"^> ([^·]+) · ([^·]+) · \[원본\]\((.+?)\)", re.MULTILINE)

    video_metas: list[VideoMeta] = []
    sections: list[str] = []
    for i, p in enumerate(md_paths, 1):
        text = p.read_text(encoding="utf-8")
        m = fm_re.match(text)
        if not m:
            log.warning("MD %s missing frontmatter, skipping", p.name)
            continue
        fm = yaml_mod.safe_load(m.group(1)) or {}
        body = m.group(2).strip()

        title_m = title_re.search(body)
        title = title_m.group(1).strip() if title_m else fm.get("video_id", "(untitled)")
        meta_m = meta_re.search(body)
        if meta_m:
            channel_name = meta_m.group(1).strip()
            try:
                published_at_utc = _dt.fromisoformat(meta_m.group(2).strip())
            except ValueError:
                published_at_utc = _dt.now(tz=UTC)
            url = meta_m.group(3).strip()
        else:
            channel_name = fm.get("channel", "")
            published_at_utc = _dt.now(tz=UTC)
            url = fm.get("source_url", "")

        video_metas.append(
            VideoMeta(
                video_id=fm.get("video_id", ""),
                channel_id="",
                channel_name=channel_name,
                channel_slug=fm.get("channel", ""),
                title=title,
                published_at_utc=published_at_utc,
                url=url,
                duration_sec=None,
            )
        )
        body_for_prompt = body if args.full_body else _extract_key_sections(body)
        sections.append(f"\n---\n### 영상 {i}: {fm.get('video_id', '')}\n\n{body_for_prompt}\n")

    user_prompt = (
        f"## 입력 — {target_date.isoformat()} 영상 분석 종합 ({len(video_metas)}건)\n\n"
        "다음은 vault에 저장된 영상별 분석 마크다운들이다. 각 영상의 frontmatter + "
        "본문을 그대로 제공한다. 이를 종합해 daily brief를 생성하라.\n"
        + "".join(sections)
    )
    system_prompt = (cfg.prompts_dir / "system_daily_brief.ko.md").read_text(encoding="utf-8")

    llm = _make_llm_client(cfg)
    log.info(
        "aggregate-only: calling LLM (timeout=%ds, prompt=%d chars)",
        cfg.claude_timeout_sec,
        len(user_prompt),
    )
    resp = llm.call(system=system_prompt, user=user_prompt, timeout_sec=cfg.claude_timeout_sec)
    payload = extract_fenced_json(resp.text)
    if not isinstance(payload, dict):
        print("LLM response was not a JSON object", file=sys.stderr)
        return 2

    market_read = (payload.get("market_read") or "").strip()
    key_insights = tuple(payload.get("key_insights") or [])
    red_team = tuple(payload.get("red_team") or []) or (
        "(영상 간 합의가 약하거나 thesis가 분산되어 통합 반론 도출이 어려움)",
    )

    rollups: list[TickerRollup] = []
    for r in payload.get("ticker_rollup") or []:
        if not isinstance(r, dict):
            continue
        per_video_raw = r.get("per_video") or []
        per_video = tuple(
            TickerRollupVideoEntry(
                video_id=str(pv.get("video_id", "")),
                direction=pv.get("direction", "언급만"),
                one_line_reason=str(pv.get("one_line_reason", "")),
            )
            for pv in per_video_raw
            if isinstance(pv, dict)
        )
        rollups.append(
            TickerRollup(
                symbol=r.get("symbol"),
                display=str(r.get("display", "")),
                in_watchlist=bool(r.get("in_watchlist", False)),
                net_direction=r.get("net_direction", "혼조"),
                mention_count=int(r.get("mention_count", len(per_video))),
                per_video=per_video,
            )
        )

    brief = DailyBrief(
        date=target_date,
        market_read=market_read,
        key_insights=key_insights,
        red_team=red_team,
        ticker_rollup=tuple(rollups),
        videos=tuple(video_metas),
        llm_meta=LLMMeta(
            model="sonnet",
            duration_ms=resp.duration_ms,
            was_retry=False,
            claude_session_id=resp.session_id,
        ),
    )

    captured_at = _dt.now(tz=cfg.tz)
    brief_path = write_daily_brief_md(
        brief, vault_daily_root=cfg.vault_daily_root, captured_at=captured_at
    )
    print(f"daily brief written: {brief_path}")

    if args.no_telegram:
        return 0

    if cfg.dry_run or not (cfg.telegram_bot_token and cfg.telegram_chat_id):
        telegram_client = DryRunTelegramClient(cfg.telegram_dryrun_dir)
    else:
        telegram_client = HttpxTelegramClient(
            bot_token=cfg.telegram_bot_token, chat_id=cfg.telegram_chat_id
        )
    result = notify_daily(brief, telegram=telegram_client)
    log.info(
        "telegram daily notify: ok=%s ids=%s err=%s",
        result.ok,
        list(result.message_ids),
        result.error,
    )

    store = IdempotencyStore(cfg.state_path)
    store.mark_daily_brief(
        target_date,
        brief_sent=result.ok,
        brief_path=str(Path(brief_path).relative_to(cfg.vault_root).as_posix()),
    )
    store.flush()
    return 0 if result.ok else 1


def _extract_key_sections(body: str) -> str:
    """Aggressively compress a video MD body to ~500-800 bytes.

    Keeps: title (truncated), 핵심 인사이트 (first 3, each ≤120 chars), 레드팀
    (first 2, each ≤120 chars), 종목 영향 ticker bullet headers (no 근거/인용).
    Drops: 3줄 헤드라인 (redundant with title), all sub-bullets, all quote blocks.
    """
    import re

    lines = body.splitlines()
    out: list[str] = []

    # Title line, truncated
    if lines:
        title = lines[0].lstrip("# ").strip()
        if len(title) > 80:
            title = title[:80] + "…"
        out.append(f"제목: {title}")

    def _grab_bullets(section_header_pattern: str, max_count: int, max_chars: int) -> list[str]:
        m = re.search(rf"^##\s+{section_header_pattern}.*?$", body, re.MULTILINE)
        if not m:
            return []
        rest = body[m.end():]
        # Cut at next ## header
        next_header = re.search(r"^##\s+", rest, re.MULTILINE)
        if next_header:
            rest = rest[: next_header.start()]
        bullets = []
        for line in rest.splitlines():
            stripped = line.strip()
            if stripped.startswith("- ") and len(bullets) < max_count:
                content = stripped[2:].strip()
                if len(content) > max_chars:
                    content = content[: max_chars - 1] + "…"
                bullets.append(f"- {content}")
        return bullets

    # 핵심 인사이트: 3건, 각 120자
    insights = _grab_bullets("🎯 핵심 인사이트", max_count=3, max_chars=120)
    if insights:
        out.append("[인사이트]")
        out.extend(insights)

    # 레드팀: 2건, 각 120자
    red_team = _grab_bullets("🚨 레드팀 시각", max_count=2, max_chars=120)
    if red_team:
        out.append("[레드팀]")
        out.extend(red_team)

    # 종목 영향: ticker 한 줄씩 (워치리스트 + 자동발견 합쳐 6개)
    sec_match = re.search(r"^##\s+📊 종목 영향.*?$", body, re.MULTILINE)
    if sec_match:
        rest = body[sec_match.end():]
        ticker_lines = []
        for line in rest.splitlines():
            stripped = line.strip()
            if stripped.startswith("- **") and len(ticker_lines) < 6:
                # Bold ticker bullet → keep as-is (truncate if huge)
                if len(stripped) > 200:
                    stripped = stripped[:200] + "…"
                ticker_lines.append(stripped)
        if ticker_lines:
            out.append("[종목 영향]")
            out.extend(ticker_lines)

    return "\n".join(out)


def _video_from_fixture(d: dict):
    from datetime import datetime

    from youtube_market_brief.domain.types import VideoMeta
    v = d["video"]
    return VideoMeta(
        video_id=v["video_id"],
        channel_id=v["channel_id"],
        channel_name=v["channel_name"],
        channel_slug=v["channel_slug"],
        title=v["title"],
        published_at_utc=datetime.fromisoformat(v["published_at_utc"]),
        url=v["url"],
        duration_sec=v.get("duration_sec"),
    )


def _transcript_from_fixture(d: dict):
    from datetime import datetime

    from youtube_market_brief.domain.types import Transcript
    t = d["transcript"]
    return Transcript(
        video_id=t["video_id"],
        language=t.get("language", "ko"),
        is_auto_generated=t.get("is_auto_generated", True),
        segments=(),
        full_text=t["full_text"],
        char_count=len(t["full_text"]),
        fetched_at=datetime.now(tz=UTC),
        was_truncated=t.get("was_truncated", False),
    )


if __name__ == "__main__":
    raise SystemExit(main())
