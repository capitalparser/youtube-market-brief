# youtube-market-brief

> 큐레이션한 YouTube 채널의 신규 영상을 자막 단위로 자동 분석해 vault에 정리하고 Telegram으로 발송한다. 매일 4회 실행되며 정리 브리핑은 다음날 아침 1회 발송한다.

## 동작 흐름

```
   YouTube Data API ─────► Discover (신규 video_id 추출)
                              │
   auto transcript ◄──── Transcribe (yt-dlp + cookies → youtube-transcript-api fallback)
                              │
                          Analyze (OpenAI gpt-4.1)
                              │
                          Write Video MD ──► vault/00_Wiki/youtube/{channel}/...
                              │
                          Notify Telegram (영상별 카드)
                              │
                  ┌──── Aggregate (당일 분석 종합) ◄── 07:00 KST 만
                  │
                  └─► Daily Brief MD + Telegram (3블록)
```

State (`state.json`) 가 video_id idempotency를 보장 — 매 실행마다 신규 영상만 처리한다. 실패한 영상(transient: ip_blocked, api_changed 등)은 다음 실행에 재시도된다.

## 자동 실행 스케줄 (GitHub Actions, KST 기준)

| 시각 | 동작 | Telegram 발송 |
|---|---|---|
| **07:00** | 어제 미처리 영상 catch-up + vault 어제 MD 전체로 brief 재구성 | 영상별 (catch-up 분) + **Daily Brief** |
| **12:00** | 당일 신규 영상 처리 | 영상별만 |
| **18:00** | 당일 신규 영상 처리 | 영상별만 |
| **23:00** | 당일 신규 영상 처리 | 영상별만 |
| 수동 (`workflow_dispatch`) | 당일 영상 + brief (default `ymb run`) | 영상별 + brief (첫 발송 시) |

> GitHub Actions cron은 best-effort라 정시 실행이 보장되지 않는다 (보통 5~30분 지연). 누락된 영상은 다음 실행에서 자동 catch-up.

## 빠른 시작 (로컬)

```bash
cd ~/vault/01_Projects/01_youtube_market_brief
uv sync
cp .env.example .env && vim .env
cp config/channels.yaml.example config/channels.yaml && vim config/channels.yaml
cp config/watchlist.yaml.example config/watchlist.yaml && vim config/watchlist.yaml

uv run ymb health                                    # LLM client 동작 확인
uv run ymb config validate                           # 환경/설정 검증
uv run ymb run --dry-run                             # E2E (Telegram dry, 실제 발송 X)
uv run ymb run                                       # 실제 발송
```

## CLI 명령어

| 명령 | 설명 |
|---|---|
| `ymb health` | LLM provider 동작 확인 (인증·연결성) |
| `ymb config show \| validate` | 설정 출력·검증 |
| `ymb run [--date YYYY-MM-DD] [--dry-run] [--force] [--no-brief]` | 일일 파이프라인 실행. `--date`는 KST 기준. `--no-brief`는 영상만 처리하고 brief 단계 skip |
| `ymb collect-urls <url-or-id>... [--date YYYY-MM-DD] [--dry-run] [--force] [--telegram]` | IP 차단/누락 대응용 수동 처리. 명시한 YouTube URL/video_id만 분석해 MD 생성 |
| `ymb aggregate-only --date YYYY-MM-DD [--no-telegram] [--full-body]` | vault에 이미 생성된 영상 sidecar를 우선 사용해 brief만 재구성·발송. sidecar가 없으면 MD parsing fallback |
| `ymb discover --handle @ch \| --channel-id UC...` | 채널 신규 영상 smoke test (분석 안 함) |
| `ymb analyze --transcript-fixture <path>` | fixture transcript JSON으로 분석만 테스트 |

## 환경 변수

`.env` 또는 GitHub Secrets로 주입.

| 변수 | 필수 | 기본값 | 설명 |
|---|---|---|---|
| `LLM_PROVIDER` | – | `api` | `api` (OpenAI) \| `cli` (`claude` CLI 로컬) |
| `OPENAI_API_KEY` | ✓ | – | `LLM_PROVIDER=api`일 때 필수 |
| `OPENAI_MODEL` | – | `gpt-4o` | 권장: `gpt-4.1` (cloud workflow는 이 값 사용) |
| `YOUTUBE_API_KEY` | ✓ | – | YouTube Data API v3 키 |
| `TELEGRAM_BOT_TOKEN` | ✓ | – | BotFather 발급 토큰 |
| `TELEGRAM_CHAT_ID` | ✓ | – | 대상 chat ID |
| `TRANSCRIPT_BACKEND` | – | `auto` | `auto` 권장. `yt_dlp`를 먼저 시도하고 retryable 실패 시 `youtube_transcript_api`로 fallback |
| `YOUTUBE_COOKIE_FILE` | – | – | Netscape cookies.txt 경로. `.secrets/youtube.cookies.txt` 같은 gitignored 위치 권장 |
| `YOUTUBE_PROXY_URL` | – | – | `yt-dlp` 및 subtitle/audio 요청용 proxy URL. IP 차단 시 가장 먼저 권장 |
| `ENABLE_STT_FALLBACK` | – | `false` | 자막 API가 막히면 오디오 다운로드 후 OpenAI STT로 transcript 생성. 비용 발생 |
| `STT_MODEL` | – | `gpt-4o-mini-transcribe` | STT fallback 모델 |
| `STT_AUDIO_MAX_MB` | – | `24` | OpenAI 파일 업로드 제한 보호용 오디오 크기 cap |
| `WEBSHARE_PROXY_USERNAME` / `_PASSWORD` | – | – | residential proxy (옵션, 미사용 시 비워둠) |
| `VAULT_ROOT_PATH` | – | walk-up 자동 탐지 | vault 루트 명시 override |
| `DRY_RUN` | – | `false` | `true`면 Telegram을 파일로 dump |
| `MAX_VIDEOS_PER_RUN` | – | `20` | 1회 실행 처리 cap |
| `TRANSCRIPT_MAX_CHARS` | – | `80000` | 자막 truncation 임계 |
| `TIMEZONE` | – | `Asia/Seoul` | RunReport.date 기준 |

## 채널 / Watchlist 설정

**`config/channels.yaml`** — 큐레이션한 채널 목록. git 추적됨 (cloud run의 source of truth).

```yaml
channels:
  - handle: '@hkglobalmarket'
    name_ko: HK Global Market
    slug: hkglobalmarket
    enabled: true
    channel_id: UCWskYkV4c4S9D__rsfOl2JA   # 처음엔 비워도 됨, 첫 실행 시 자동 resolve + persist
```

**`config/watchlist.yaml`** — 종목 watchlist (gitignored, 개인 정보).

```yaml
tickers:
  - symbol: '005930'
    market: KOSPI
    name_ko: 삼성전자
    name_en: Samsung Electronics
    sector: semiconductors      # 허용값: semiconductors, software_ai_services, tech_hardware, financials,
                                #          power_utilities, industrials_defense, energy, materials,
                                #          consumer_discretionary, consumer_staples
    aliases: ['samsung', 'sec']
```

watchlist가 비어있으면 LLM 자동 발견 ticker만 출력에 들어간다. `sector` 미입력 시 LLM이 발견한 값을 그대로 사용한다.

## Cloud 실행 (GitHub Actions)

`.github/workflows/digest.yml` 가 4개 cron + 수동 `workflow_dispatch` 로 실행된다. 결과 MD와 `state.json` 은 rclone으로 Google Drive에 동기화 (Drive Desktop이 로컬 vault로 풀링).

로컬 rescue runner는 추가로 `02_Areas/Market_Insights/`를 Drive에 read-only sync하고, 모바일에서 한 파일로 읽기 쉬운 `02_Areas/Market_Insights/_mobile.md`를 생성한다.

**필요한 GH Secrets** (Repo → Settings → Secrets and variables → Actions):

| Secret | 내용 |
|---|---|
| `OPENAI_API_KEY` | OpenAI API 키 |
| `YOUTUBE_API_KEY` | YouTube Data API v3 키 |
| `TELEGRAM_BOT_TOKEN` | BotFather 토큰 |
| `TELEGRAM_CHAT_ID` | 대상 chat ID |
| `YOUTUBE_COOKIES` | **Netscape 형식 cookies.txt 전체 내용** (yt-dlp 인증용, 클라우드 IP 우회의 핵심) |
| `YOUTUBE_PROXY_URL` | (권장) YouTube 요청용 residential proxy URL |
| `DRIVE_SERVICE_ACCOUNT_JSON` | Google Cloud 서비스 계정 키(JSON 전체) |
| `GDRIVE_OUTPUT_FOLDER_ID` | Drive 출력 폴더 ID — 서비스 계정에 Editor 공유됨 |
| `WEBSHARE_PROXY_USERNAME` / `_PASSWORD` | (옵션) — 사용 안 하면 비워둠 |

**Drive 폴더 구조** (서비스 계정이 쓸 폴더 안):

```
{root_folder}/
├── config/                                    # cloud run이 매번 pull (watchlist만)
│   └── watchlist.yaml
├── 00_Wiki/youtube/                           # cloud run이 push
│   ├── {channel_slug}/{YYYY-MM-DD}__*.md
│   └── _daily/{YYYY-MM-DD}_brief.md
├── 02_Areas/Market_Insights/                  # local rescue/sync가 push
│   ├── _dashboard.md
│   ├── _mobile.md                             # Drive 모바일용 단일 파일 요약
│   ├── _mobile.html                           # private rich 모바일 읽기앱
│   ├── themes/*.md
│   └── sectors/*.md
└── Harness/sink/youtube_market_brief/
    └── state.json                             # idempotency state (cloud read+write)
```

**GitHub Pages 공개 뷰**: 로컬 sync는 private rich HTML과 별도로 sanitized public HTML을 `docs/market-insights/index.html`에 생성한다. `.github/workflows/pages.yml`은 이 디렉터리만 Pages artifact로 배포한다. raw 캡처·자막·sidecar·원본 card Markdown은 public repo에 복사하지 않는다.

> `channels.yaml` 은 git tracked — Drive에서 pull하지 않는다. 채널 목록 변경은 git commit으로.

## YouTube 쿠키 갱신 (트러블슈팅)

YouTube는 GitHub Actions의 클라우드 IP를 봇으로 차단할 수 있다. 기본값 `TRANSCRIPT_BACKEND=auto`는 `yt-dlp` + 쿠키 인증을 먼저 시도하고, retryable 실패 시 `youtube-transcript-api`로 한 번 더 시도한다. 쿠키는 **수 주 ~ 몇 달 단위**로 만료된다. 다음 에러가 다시 보이면 갱신 필요:

```
ERROR: [youtube] xxxx: Sign in to confirm you're not a bot.
```

**갱신 절차:**

1. Chrome에 [Get cookies.txt LOCALLY](https://chrome.google.com/webstore/detail/get-cookiestxt-locally) 확장 설치
2. **YouTube 로그인 상태**에서 `youtube.com` 열기
3. 확장 아이콘 클릭 → "Export" → Netscape format으로 저장
4. 저장된 파일에 `LOGIN_INFO`, `__Secure-1PSID`, `__Secure-1PAPISID`, `SAPISID` 가 포함되어 있는지 확인
5. 파일 전체 내용을 GH Secret `YOUTUBE_COOKIES` 에 붙여넣어 업데이트 (multi-line 그대로 OK)
6. `gh workflow run digest.yml` 으로 수동 실행해 검증

로컬에서 긴급 수동 처리:

```bash
TRANSCRIPT_BACKEND=auto \
YOUTUBE_COOKIE_FILE=.secrets/youtube.cookies.txt \
uv run ymb collect-urls 'https://www.youtube.com/watch?v=VIDEO_ID' --dry-run --force
```

IP 차단이 계속되면 두 가지 중 하나를 켠다:

```bash
# 1) 권장: residential proxy를 YouTube 요청 전체에 적용
YOUTUBE_PROXY_URL='http://USER:PASS@host:port' uv run ymb run --date YYYY-MM-DD --force

# 2) 최후 fallback: 자막 API 대신 오디오 -> OpenAI STT
ENABLE_STT_FALLBACK=true uv run ymb run --date YYYY-MM-DD --force
```

**진단 로그**: workflow의 "Write YouTube cookies" 단계가 `cookies written (N lines, M bytes)` + `first_line_starts_with_hash=1` + `has_youtube_domain=N` 을 출력한다. 모두 정상값(특히 `has_youtube_domain` ≥ 20)이어야 한다.

## 출력 위치

- 영상별 MD: `{vault_root}/00_Wiki/youtube/{channel_slug}/{YYYY-MM-DD}__{video_slug}.md`
- 영상별 분석 sidecar: `{vault_root}/00_Wiki/youtube/{channel_slug}/{YYYY-MM-DD}__{video_slug}.analysis.json` (P2 propagation source)
- 일일 브리핑 MD: `{vault_root}/00_Wiki/youtube/_daily/{YYYY-MM-DD}_brief.md`
- 일일 브리핑 sidecar: `{vault_root}/00_Wiki/youtube/_daily/{YYYY-MM-DD}_brief.analysis.json`
- 일일 propagation proposal: `{vault_root}/Harness/sessions/entity_propagation/{YYYY-MM-DD}/{YYYY-MM-DD}_brief.proposal.md` (proposal-only, 카드 직접 수정 없음)
- 상태 파일: `{vault_root}/Harness/sink/youtube_market_brief/state.json` (gitignored)
- 로그: `{vault_root}/Harness/logs/youtube_market_brief/{YYYY-MM-DD}.log` (gitignored)

> **v1.5 schema (2026-05-16~):** `key_insights` / `red_team`은 object 형태 `{text, why_important, structural_shift, pattern_connection, counter_signal, workflow_implication, signal_density, sector_tags, theme_tags}`. ticker에는 `sector_tag` 단일값. 자세한 내용은 `docs/adr/0006-prompt-persona-schema-realignment.md` 참조.

## 디렉토리

```
.
├── .github/workflows/digest.yml          # GH Actions cron (4x/day) + manual
├── config/
│   ├── channels.yaml                     # 채널 목록 (git tracked)
│   └── watchlist.yaml                    # 종목 watchlist (gitignored)
├── prompts/
│   ├── system_video_analysis.ko.md
│   └── system_daily_brief.ko.md
├── src/youtube_market_brief/
│   ├── cli.py                            # ymb 엔트리포인트
│   ├── orchestrator.py                   # 파이프라인 조립 + RunReport
│   ├── config.py                         # AppConfig + load_channels/watchlist
│   ├── _clients/                         # YouTube Data, Transcript, LLM, Telegram (Protocol + impl)
│   ├── pipeline/                         # discover / transcribe / analyze / write_video / aggregate / notify
│   ├── domain/                           # types, watchlist 매칭, slugify (client-free)
│   └── state/store.py                    # JSON idempotency store (atomic write)
├── tests/                                # pytest, in-memory fakes
├── plans/                                # Superpowers writing-plans 산출물
└── docs/adr/                             # 아키텍처 결정 기록
```

## 문서 포인터

| 파일 | 용도 |
|---|---|
| `CLAUDE.md` | 프로젝트 시스템 컨텍스트 + 인터페이스 계약 |
| `CONTEXT.md` | 도메인 사전 (Ubiquitous Language) |
| `HANDOFF.md` | Codex CLI 인수 가이드 |
| `plans/2026-05-07-initial-plan.md` | 최신 실행 plan |
| `docs/adr/0001-module-structure.md` | 모듈 구조 결정 |
| `docs/adr/0002-idempotency-state.md` | 멱등성/state 결정 |
| `docs/adr/0005-llm-client-cloud-execution.md` | OpenAI API 채택 + cloud 실행 설계 |

## 라이선스

Private (capitalparser).
