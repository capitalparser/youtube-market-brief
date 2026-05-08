# CONTEXT.md — 01_youtube_market_brief

PAS의 Ubiquitous Language를 재사용하고, 본 도메인(시장·종목 분석)의 용어를 시드한다.

## 1. 프로젝트 정의

`01_youtube_market_brief`는 사용자가 큐레이션한 YouTube 채널들의 신규 영상을 매일 자동 수집·분석하여 (1) 영상별 정리 노트를 vault에 작성하고 (2) 일일 시장 브리핑을 합성하며 (3) Telegram으로 발송하는 도메인 Runner이다. PAS의 인프라(Runner YAML, Wiki frontmatter 컨벤션, Sink/Logs)를 차용한다.

## 2. Ubiquitous Language

### 2.1 PAS에서 재사용하는 용어 (정의는 PAS CONTEXT.md 참조)

- Runner, Trigger(Schedule), Inbox, Sink, Logs, Tier, Ingestion, Promotion

### 2.2 본 프로젝트 신규 용어

| 용어 | 정의 |
|------|------|
| Channel | 사용자가 `config/channels.yaml`에 등록한 YouTube 채널. `channel_id`(UCxxx) 또는 handle(@xxx)로 식별 |
| Channel Slug | 파일경로 안전 키. `channels.yaml`의 `slug` 필드가 우선(deterministic). 미지정 시 자동 생성 |
| Video | 채널에 업로드된 영상 1건. `video_id`로 식별. idempotency PK |
| Transcript | 영상의 자막. `language`, `is_auto_generated` 필드 보유. 없으면 `TranscriptSkip` |
| Watchlist | 사용자가 `config/watchlist.yaml`에 사전 등록한 종목 목록. `symbol, market, name_ko, aliases` |
| Watchlist Hit | 영상 분석 결과 watchlist 등록 ticker가 의미 있게 언급됨 (`quotes` 필수) |
| Auto-discovered Ticker | watchlist 미등록이지만 LLM이 영상에서 발견한 ticker. `confidence` 보유 |
| Ticker Mention | 영상 내 단일 ticker에 대한 분석 단위. `direction`(긍정적/중립/부정적/언급만), `reasoning`, `quotes`, `confidence` |
| Direction | ticker 영향 방향. `긍정적`/`중립`/`부정적`/`언급만` 4값 |
| Net Direction | 일일 브리핑에서 같은 ticker의 영상 간 방향 통합. `긍정적`/`중립`/`부정적`/`혼조` 4값 |
| Key Insights | 영상의 핵심 인사이트 3-5건 (LLM 도출) |
| Red Team | 영상 thesis에 대한 반대 시각·리스크·약점·의문점 2-4건 (LLM 도출). devil's advocate |
| Video Analysis | 1개 영상의 분석 결과 단위. `transcript_summary, tickers, watchlist_hits, tier` |
| Daily Brief | 당일 모든 Video Analysis의 합성. `market_read, key_insights, red_team, ticker_rollup` |
| Ticker Rollup | 일일 브리핑에서 같은 ticker가 여러 영상에 언급될 때의 집계. `net_direction, mention_count, per_video[]` |
| Run | Runner의 1회 실행. cron 또는 수동. `RunReport`로 결과 보고 |
| Run Report | 1 Run의 실행 결과. `discovered, processed, skipped_*, failed[], duration_sec` |

## 3. 컴포넌트 흐름

```
[Trigger:Schedule 07:00 KST]
        │
        ▼
   orchestrator.run(date)
        │
        ▼
discover ──▶ list[VideoMeta]              (YouTube Data v3)
        │  filtered by IdempotencyStore
        ▼
for each Video:
  transcribe  ──▶ Transcript | TranscriptSkip   (youtube-transcript-api)
  analyze     ──▶ VideoAnalysis                  (claude CLI subprocess)
  watchlist   ──▶ VideoAnalysis (hits filtered)  (alias matcher)
  write_video ──▶ Path("00_Wiki/youtube/{slug}/{date}__{video}.md")
  notify(per_video) ──▶ NotifyResult             (Telegram)
  IdempotencyStore.mark(video_id)
        │
        ▼ (after loop, if processed > 0)
aggregate   ──▶ DailyBrief + Path("00_Wiki/youtube/_daily/{date}_brief.md")
notify(daily) ──▶ NotifyResult
        │
        ▼
RunReport ──▶ logs + stderr
```

## 4. 비기능 요구사항

- 실패 격리: per-video try/except, run-level continue
- 재실행 안전: video_id idempotency. 동일 video 재투입 시 skip. daily MD 존재 시 미덮어씀(`--force` 토글)
- 검증 분리: ingestion 출력 검증과 LLM 응답 스키마 검증을 분리 (`pipeline/transcribe.py` vs `pipeline/analyze.py`)
- 로컬 우선: 모든 처리는 로컬에서. claude CLI는 사용자 로그인 활용 (API 키 없음). YouTube/Telegram만 외부 호출
- 시간대 일관: 비교는 항상 tz-aware datetime. config `timezone="Asia/Seoul"` 고정

## 5. 기준 결정 (현재 시점)

- LLM 호출: `claude -p --output-format json --model sonnet --max-turns 1` subprocess
- 자막 수집: `youtube-transcript-api` (Whisper fallback 비채택, MVP)
- 출력 frontmatter 필수 9필드: `source_url, source_type, captured_at, tier, tags, video_id, channel, watchlist_hits, was_truncated`
- Tier 규칙: `watchlist_hits` 비면 T2 (Light), 있으면 T3 (Deep)
- Telegram 메시지 3블록: 핵심 인사이트 + 레드팀 시각 + 종목 영향
- 호출 회수 cap: `max_videos_per_run=20`

## 6. 비범위

- Whisper ASR (Transcript fallback)
- Map-reduce chunking (긴 영상)
- 자동 발견 ticker symbol 해상도 ("엔비디아"→"NVDA")
- Web UI / dashboard
- 다중 사용자

---

_Last updated: 2026-05-07 (Phase 0)_
