# youtube-market-brief

> 매일 KST 07:00, 사용자가 큐레이션한 YouTube 채널들의 신규 영상을 자동 분석하여 vault에 정리하고 Telegram으로 발송한다.

## 사용자 원문

> 유튜브의 내가 원하는 채널들을 api로 스크립트 등을 api로 따와서, 해당 채널의 영상들을 일별로 요약 / 핵심 내용 정리 / 특정 종목에 대한 분석 및 영향을 정리하여 md파일로 정리 및 텔레그램 메시지 전송하는 툴을 개발하자

## 개요

| 항목 | 값 |
|------|------|
| 트리거 | cron `0 7 * * *` (KST) |
| 자막 수집 | YouTube Data API v3 (메타) + youtube-transcript-api (자막) |
| 분석 | Anthropic Messages API (`claude-sonnet-4-6`, prompt caching) — cloud-runnable. 로컬 fallback으로 `claude` CLI도 선택 가능 (`LLM_PROVIDER=cli`). |
| 출력 | 영상별 MD `00_Wiki/youtube/{channel_slug}/{YYYY-MM-DD}__{video_slug}.md` + 일일 브리핑 `_daily/{YYYY-MM-DD}_brief.md` |
| 발송 | Telegram Bot API. 영상 단위 + 일일 브리핑. 3블록 구조(핵심 인사이트 + 레드팀 시각 + 종목 영향) |

## 빠른 시작

```bash
cd ~/vault/01_Projects/01_youtube_market_brief
uv sync
cp .env.example .env && vim .env                 # YOUTUBE_API_KEY + TELEGRAM_BOT_TOKEN/CHAT_ID
cp config/channels.yaml.example config/channels.yaml && vim config/channels.yaml
cp config/watchlist.yaml.example config/watchlist.yaml && vim config/watchlist.yaml

uv run ymb health                                 # claude CLI 동작 확인
uv run ymb run --dry-run --date 2026-05-06        # E2E 시연 (Telegram만 dry)
uv run ymb run                                    # 실제 발송
```

## 문서 구조

| 파일 | 용도 |
|------|------|
| `CLAUDE.md` | 프로젝트 시스템 컨텍스트 + 인터페이스 계약 |
| `CONTEXT.md` | 도메인 사전 (Ubiquitous Language) |
| `HANDOFF.md` | Codex CLI 인수 가이드 |
| `plans/2026-05-07-initial-plan.md` | 최신 실행 plan |
| `docs/adr/0001-module-structure.md` | 모듈 구조 결정 |
| `docs/adr/0002-idempotency-state.md` | 멱등성/state 결정 |

## 의존성

- Python 3.12.7 + uv
- 외부 API: Anthropic Messages API (key 필요), YouTube Data API v3 (key), Telegram Bot API (token + chat_id)
- 로컬 fallback: `claude` CLI (옵션, `LLM_PROVIDER=cli` 일 때)

## 출력 위치

- 영상별 MD: `{vault_root}/00_Wiki/youtube/{channel_slug}/{YYYY-MM-DD}__{video_slug}.md`
- 일일 브리핑 MD: `{vault_root}/00_Wiki/youtube/_daily/{YYYY-MM-DD}_brief.md`
- 상태 파일: `{vault_root}/Harness/sink/youtube_market_brief/state.json` (gitignored)
- 로그: `{vault_root}/Harness/logs/youtube_market_brief/{YYYY-MM-DD}.log` (gitignored)

`vault_root`는 `VAULT_ROOT_PATH` env로 override 가능. 기본은 `~/vault` walk-up 자동 탐지.

## Cloud 실행 (GitHub Actions cron)

`.github/workflows/digest.yml`이 매일 KST 07:00 GH Actions runner에서 자동 실행. 결과 MD는 Google Drive에 업로드되고 사용자 Drive Desktop이 로컬에 동기화.

**필요한 GH Secrets** (Settings → Secrets and variables → Actions):

| Secret | 내용 |
|---|---|
| `ANTHROPIC_API_KEY` | Anthropic Console에서 발급 |
| `YOUTUBE_API_KEY` | Google Cloud Console |
| `TELEGRAM_BOT_TOKEN` | BotFather가 발급한 token |
| `TELEGRAM_CHAT_ID` | 발송 대상 채팅 ID |
| `GDRIVE_SERVICE_ACCOUNT_JSON` | Google Cloud 서비스 계정 키(JSON 전체 내용) |
| `GDRIVE_OUTPUT_FOLDER_ID` | Drive 폴더 ID — 서비스 계정에 Editor 권한 공유된 폴더 |

**Drive 폴더 구조** (서비스 계정이 쓸 폴더 안에):

```
{root_folder}/
├── config/                                   # cloud run이 매번 pull
│   ├── channels.yaml                         # 사용자가 업로드 (없어도 무방, 로컬 config 사용)
│   └── watchlist.yaml
├── 00_Wiki/youtube/                          # cloud run이 push (Drive Desktop이 로컬 동기화)
│   ├── {channel_slug}/{YYYY-MM-DD}__*.md
│   └── _daily/{YYYY-MM-DD}_brief.md
└── Harness/sink/youtube_market_brief/
    └── state.json                            # idempotency state (cloud read+write)
```

**서비스 계정 만들기**:

1. Google Cloud Console → IAM → Service Accounts → Create
2. Drive API 활성화 (Library에서)
3. 서비스 계정 키 발급 (JSON) → GH Secret `GDRIVE_SERVICE_ACCOUNT_JSON`
4. Drive에서 출력용 폴더 생성, 서비스 계정 이메일에 Editor 권한 공유
5. 폴더 ID 복사 → GH Secret `GDRIVE_OUTPUT_FOLDER_ID`

자세한 설계 근거: `docs/adr/0005-llm-client-cloud-execution.md`.
