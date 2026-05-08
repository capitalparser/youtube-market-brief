# 01_youtube_market_brief

> 매일 KST 07:00, 사용자가 큐레이션한 YouTube 채널들의 신규 영상을 자동 분석하여 vault에 정리하고 Telegram으로 발송한다.

## 사용자 원문

> 유튜브의 내가 원하는 채널들을 api로 스크립트 등을 api로 따와서, 해당 채널의 영상들을 일별로 요약 / 핵심 내용 정리 / 특정 종목에 대한 분석 및 영향을 정리하여 md파일로 정리 및 텔레그램 메시지 전송하는 툴을 개발하자

## 개요

| 항목 | 값 |
|------|------|
| 트리거 | cron `0 7 * * *` (KST) |
| 자막 수집 | YouTube Data API v3 (메타) + youtube-transcript-api (자막) |
| 분석 | `claude` CLI subprocess (`-p --output-format json --model sonnet`). Anthropic API 키 미사용 |
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
- `claude` CLI (사용자 Claude Code 로그인 활성)
- 외부 API: YouTube Data API v3 (key), Telegram Bot API (token + chat_id)

## 출력 위치

- 영상별 MD: `~/vault/00_Wiki/youtube/{channel_slug}/{YYYY-MM-DD}__{video_slug}.md`
- 일일 브리핑 MD: `~/vault/00_Wiki/youtube/_daily/{YYYY-MM-DD}_brief.md`
- 상태 파일: `~/vault/Harness/sink/youtube_market_brief/state.json` (gitignored)
- 로그: `~/vault/Harness/logs/youtube_market_brief/{YYYY-MM-DD}.log` (gitignored)
