"""Application configuration: env + YAML."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml
from dotenv import load_dotenv

from youtube_market_brief.domain.types import ChannelConfig, Watchlist, WatchlistEntry


@dataclass
class AppConfig:
    project_root: Path
    vault_root: Path

    youtube_api_key: str
    telegram_bot_token: str
    telegram_chat_id: str

    llm_provider: str
    openai_api_key: str
    openai_model: str

    claude_bin: str
    claude_model: str
    claude_timeout_sec: int

    webshare_proxy_username: str
    webshare_proxy_password: str

    transcript_backend: str  # "youtube_transcript_api" | "yt_dlp"
    youtube_cookie_file: str  # path to Netscape cookies.txt (optional)

    dry_run: bool
    log_level: str
    transcript_max_chars: int
    max_videos_per_run: int
    skip_shorts: bool
    timezone: str

    channels_path: Path
    watchlist_path: Path
    prompts_dir: Path

    @property
    def vault_youtube_root(self) -> Path:
        return self.vault_root / "00_Wiki" / "youtube"

    @property
    def vault_daily_root(self) -> Path:
        return self.vault_root / "00_Wiki" / "youtube" / "_daily"

    @property
    def state_path(self) -> Path:
        return self.vault_root / "Harness" / "sink" / "youtube_market_brief" / "state.json"

    @property
    def telegram_dryrun_dir(self) -> Path:
        return self.vault_root / "Harness" / "sink" / "youtube_market_brief" / "telegram_dryrun"

    @property
    def logs_dir(self) -> Path:
        return self.vault_root / "Harness" / "logs" / "youtube_market_brief"

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)


def load_app_config(
    *,
    project_root: Path | None = None,
    vault_root: Path | None = None,
    env_path: Path | None = None,
) -> AppConfig:
    project_root = project_root or Path(__file__).resolve().parents[2]
    if env_path is None:
        env_path = project_root / ".env"
    if env_path.exists():
        load_dotenv(env_path)
    if vault_root is None:
        env_vault = os.environ.get("VAULT_ROOT_PATH", "").strip()
        if env_vault:
            vault_root = Path(env_vault).expanduser().resolve()
        else:
            vault_root = _detect_vault_root(project_root)

    return AppConfig(
        project_root=project_root,
        vault_root=vault_root,
        youtube_api_key=os.environ.get("YOUTUBE_API_KEY", ""),
        telegram_bot_token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
        telegram_chat_id=os.environ.get("TELEGRAM_CHAT_ID", ""),
        llm_provider=os.environ.get("LLM_PROVIDER", "api").strip().lower(),
        openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
        openai_model=os.environ.get("OPENAI_MODEL", "gpt-4o"),
        claude_bin=os.environ.get("CLAUDE_BIN", "claude"),
        claude_model=os.environ.get("CLAUDE_MODEL", "sonnet"),
        claude_timeout_sec=int(os.environ.get("CLAUDE_TIMEOUT_SEC", "300")),
        webshare_proxy_username=os.environ.get("WEBSHARE_PROXY_USERNAME", ""),
        webshare_proxy_password=os.environ.get("WEBSHARE_PROXY_PASSWORD", ""),
        transcript_backend=os.environ.get("TRANSCRIPT_BACKEND", "youtube_transcript_api"),
        youtube_cookie_file=os.environ.get("YOUTUBE_COOKIE_FILE", ""),
        dry_run=os.environ.get("DRY_RUN", "false").lower() == "true",
        log_level=os.environ.get("LOG_LEVEL", "INFO"),
        transcript_max_chars=int(os.environ.get("TRANSCRIPT_MAX_CHARS", "80000")),
        max_videos_per_run=int(os.environ.get("MAX_VIDEOS_PER_RUN", "20")),
        skip_shorts=os.environ.get("SKIP_SHORTS", "true").lower() == "true",
        timezone=os.environ.get("TIMEZONE", "Asia/Seoul"),
        channels_path=project_root / "config" / "channels.yaml",
        watchlist_path=project_root / "config" / "watchlist.yaml",
        prompts_dir=project_root / "prompts",
    )


def _detect_vault_root(project_root: Path) -> Path:
    """Walk up from project_root to find the vault root.

    Vault is identified by a CLAUDE.md (or legacy AGENTS.md) marker plus 00_Wiki/.
    """
    cur = project_root
    for _ in range(8):
        has_marker = (cur / "CLAUDE.md").exists() or (cur / "AGENTS.md").exists()
        if has_marker and (cur / "00_Wiki").exists():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    return Path.home() / "vault"


def load_channels(path: Path) -> list[ChannelConfig]:
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    raw_channels = data.get("channels") or []
    out: list[ChannelConfig] = []
    for c in raw_channels:
        out.append(
            ChannelConfig(
                channel_id=c.get("channel_id"),
                handle=c.get("handle"),
                name_ko=c.get("name_ko") or c.get("handle") or c.get("channel_id") or "(unnamed)",
                slug=(c.get("slug") or "").strip(),
                enabled=bool(c.get("enabled", True)),
                notes=c.get("notes"),
            )
        )
    return out


def load_watchlist(path: Path) -> Watchlist:
    if not path.exists():
        return Watchlist(entries=())
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    raw = data.get("tickers") or []
    entries: list[WatchlistEntry] = []
    for t in raw:
        entries.append(
            WatchlistEntry(
                symbol=str(t.get("symbol", "")).strip(),
                market=t.get("market", "ETC"),
                name_ko=t.get("name_ko", "").strip(),
                name_en=(t.get("name_en") or None),
                aliases=tuple(a for a in (t.get("aliases") or []) if isinstance(a, str)),
            )
        )
    return Watchlist(entries=tuple(e for e in entries if e.symbol))


def persist_resolved_channel_id(channels_path: Path, slug: str, channel_id: str) -> None:
    """Update channels.yaml to record the resolved channel_id for an entry by slug.

    No-op if file doesn't exist or slug not found. Best-effort — log on failure.
    """
    if not channels_path.exists():
        return
    data = yaml.safe_load(channels_path.read_text(encoding="utf-8")) or {}
    raw = data.get("channels") or []
    changed = False
    for c in raw:
        if (c.get("slug") or "").strip() == slug and not c.get("channel_id"):
            c["channel_id"] = channel_id
            changed = True
            break
    if changed:
        channels_path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
