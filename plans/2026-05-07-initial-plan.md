# Plan — `01_youtube_market_brief`

## Context

사용자(K-IFRS 감사인 / AX Node 매니저)는 매일 자신이 큐레이션한 YouTube 채널들의 신규 영상에서 **시장·종목 정보를 자동 추출**해 vault에 정리하고 Telegram으로 받아보고자 한다. 현재 `~/vault/01_Projects/00_personal_agent_system` (PAS)의 인프라(Runner YAML 스키마, Wiki frontmatter 컨벤션, Harness sink/logs, Codex 인계 패턴)는 마련됐으나 **첫 도메인 Runner**가 비어 있다. 본 프로젝트는 PAS 인프라 위에서 동작하는 첫 구체 Runner이며, 단순 ingestion을 넘어 **종목 분석 + Telegram 전송**까지 결합되므로 PAS 본체가 아닌 신규 프로젝트로 분리한다(PAS CONTEXT.md "비범위" 위배 회피).

목표 산출: 매일 KST 07:00 자동 실행되어 (1) 채널별 영상 메타 + 자막 수집 → (2) Claude Sonnet 4.6로 요약·종목 영향 분석 → (3) `00_Wiki/youtube/`에 영상별 MD + 일일 종합 브리핑 작성 → (4) Telegram에 영상별 알림 + 일일 브리핑 헤드라인 push.

## Decisions Locked (사용자 확인)

| 영역 | 결정 |
|---|---|
| 프로젝트 위치 | `~/vault/01_Projects/01_youtube_market_brief/` (신규부터 `01_/02_/...` 넘버링; 기존 4개 프로젝트는 그대로) |
| 자막 수집 | YouTube Data API v3(메타데이터) + `youtube-transcript-api`(자막). Whisper fallback 비채택(MVP) |
| LLM 호출 방식 | **Anthropic API 키 미사용**. 기존 vault Runner 패턴대로 `claude` CLI를 subprocess로 호출(`claude -p <prompt> --output-format json`). 사용자의 Claude Code 로그인을 그대로 활용 → API 키 관리 불필요, 별도 청구 없음 |
| 출력 | 영상별 MD: `00_Wiki/youtube/{channel_slug}/{YYYY-MM-DD}__{video_slug}.md` · 일일 브리핑: `00_Wiki/youtube/_daily/{YYYY-MM-DD}_brief.md` · Telegram: 영상 단위 + 일일 브리핑 (둘 다, 핵심 인사이트 + 레드팀 분석 + 종목 영향 3블록 구조) |
| 스케줄 | KST 07:00 daily (cron `0 7 * * *` `Asia/Seoul`) |
| 워치리스트 | `config/watchlist.yaml` 사전 등록 + LLM 자동 식별 하이브리드 |

## Project Layout

```
~/vault/01_Projects/01_youtube_market_brief/
├── CLAUDE.md            # 프로젝트 시스템 컨텍스트 (PAS의 형식 차용)
├── CONTEXT.md           # 도메인 사전 (Ubiquitous Language 시드: PAS 용어 재사용)
├── HANDOFF.md           # PAS HANDOFF.md 그대로 복사
├── README.md            # 본 plan 요약 + 사용자 원문 보존
├── docs/adr/
│   ├── 0001-module-structure.md
│   └── 0002-idempotency-state.md
├── plans/
│   └── 2026-05-07-initial-plan.md      # 본 plan 사본
├── config/
│   ├── channels.yaml.example
│   └── watchlist.yaml.example
├── prompts/
│   ├── system_video_analysis.ko.md
│   └── system_daily_brief.ko.md
├── src/youtube_market_brief/
│   ├── __init__.py, __main__.py, cli.py, orchestrator.py, config.py, logging_setup.py
│   ├── domain/{types,slugify,watchlist,markdown,daily_brief,telegram_format}.py
│   ├── pipeline/{discover,transcribe,analyze,write_video,aggregate,notify}.py
│   ├── state/store.py
│   └── _clients/{youtube_data,transcript,llm,telegram}.py
├── tests/
│   ├── fakes/, fixtures/{transcripts,llm_responses,youtube_data,golden}
│   └── unit/, integration/, test_e2e_smoke.py
├── pyproject.toml       # uv-managed
├── .python-version      # 3.12.7
└── .env.example
```

또한 신규 파일:
- `~/vault/Harness/runners/youtube_market_brief.yaml` — Runner YAML (cron 등록 메타)

## Module Responsibilities (single-responsibility, DI via `Protocol`)

| 모듈 | 입력 → 출력 | 외부 의존 |
|---|---|---|
| `pipeline/discover.py` | `channels.yaml` + `IdempotencyStore` → `list[VideoMeta]` (미처리 신규 영상만) | YouTube Data API v3 |
| `pipeline/transcribe.py` | `VideoMeta` → `Transcript \| TranscriptSkip` | youtube-transcript-api |
| `pipeline/analyze.py` | `Transcript` + `Watchlist` → `VideoAnalysis` | `claude` CLI subprocess |
| `domain/watchlist.py` | LLM raw tickers + `Watchlist` → `WatchlistHits` (alias 매칭, 충돌 가드) | — |
| `pipeline/write_video.py` | `VideoAnalysis` → MD 파일 경로 | 파일I/O |
| `pipeline/aggregate.py` | `list[VideoAnalysis]` → `DailyBrief` + MD | `claude` CLI subprocess |
| `pipeline/notify.py` | `VideoAnalysis` 또는 `DailyBrief` → `NotifyResult[]` | Telegram Bot API |
| `state/store.py` | path → atomic JSON store (get/put/flush) | 파일I/O |
| `orchestrator.py` | `AppConfig` + run mode → `RunReport` (조립 + 실패 격리) | 위 전부 |
| `cli.py` | argv → exit code | `orchestrator` |

핵심 원칙:
- `_clients/*`는 모두 `typing.Protocol` 인터페이스 노출 → 테스트는 `tests/fakes/` in-memory 대체
- `pipeline/*`은 client를 인자로 DI. 전역 싱글턴 금지
- `domain/*`은 client-free deterministic. snapshot 테스트 가능
- `prompts/*.md`는 코드 외부에 두어 prompt cache 단위(파일 경계)가 명확하게 보이게

## Core Types (`domain/types.py`, frozen dataclass)

```text
VideoMeta(video_id, channel_id, channel_name, channel_slug, title, published_at_utc, url, duration_sec)
Transcript(video_id, language, is_auto_generated, segments, full_text, char_count, fetched_at)
TranscriptSkip(video_id, reason: Literal["no_captions"|"disabled"|"geo_blocked"|"api_changed"|"timeout"], detail)
WatchlistEntry(symbol, market: Literal["KOSPI"|"KOSDAQ"|"NYSE"|"NASDAQ"|"ETC"], name_ko, name_en, aliases)
TickerMention(symbol|None, display, in_watchlist, direction: Literal["긍정적"|"중립"|"부정적"|"언급만"], reasoning, quotes[≤2], confidence: Literal["high"|"medium"|"low"])
VideoAnalysis(video, transcript_summary{headline_3line, key_insights[3-5], red_team[2-4], chars_used, was_truncated}, tickers[], watchlist_hits[symbols], tier: "T2"|"T3", tags[], llm_meta{model, claude_session_id, duration_ms, was_retry}, generated_at)
DailyBrief(date, market_read, key_insights[3-5], red_team[2-4], ticker_rollup[TickerRollup], videos[VideoMeta], llm_meta)
TickerRollup(symbol, display, in_watchlist, net_direction: "긍정적"|"중립"|"부정적"|"혼조", mention_count, per_video[(video_id, direction, one_line_reason)])
NotifyResult(target: "per_video"|"daily", ok, message_ids[], error|None)
RunReport(date, discovered, processed, skipped_no_caption, skipped_idempotent, failed[(video_id, error_class, msg)], total_cost_usd, duration_sec)
```

`Transcript | TranscriptSkip` union으로 "캡션 없음"이 정상 흐름임을 타입에서 강제.
`tier`는 `domain/`이 결정 — 정책 단일 소스. `watchlist_hits`가 비면 T2, 있으면 T3 (`00_Wiki/CLAUDE.md` Tier 규칙 매핑).
`red_team` 필드는 LLM이 영상 주장의 **반대 시각·리스크·약점·의문점** 2-4건을 도출 (devil's advocate). 사용자가 영상 메인 thesis에 휩쓸리지 않도록 강제.

## Configuration Schemas

`config/channels.yaml`:
```yaml
channels:
  - channel_id: UCxxxxxxxxxxxxxxxxxxxxxx   # 미지정 시 handle로 1회 resolve 후 자동 기록
    handle: "@aekyung_invest"
    name_ko: "애경 투자노트"
    slug: "aekyung_invest"                  # 파일경로 안정 키 (deterministic)
    enabled: true
    notes: "거시 + 미국주식"
```

`config/watchlist.yaml`:
```yaml
tickers:
  - symbol: "005930"
    market: KOSPI
    name_ko: "삼성전자"
    name_en: "Samsung Electronics"
    aliases: ["삼전", "삼성전"]
```

`.env.example`:
```
YOUTUBE_API_KEY=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
CLAUDE_BIN=claude                 # claude CLI 경로 (기본 PATH 탐색)
CLAUDE_MODEL=sonnet               # claude -p --model 인자 (기본 'sonnet')
CLAUDE_TIMEOUT_SEC=300            # 단일 호출 타임아웃
DRY_RUN=false
LOG_LEVEL=INFO
```

ANTHROPIC_API_KEY는 **사용하지 않는다**. Claude Code CLI의 사용자 로그인 세션을 그대로 활용.

`AppConfig` 추가 필드: `transcript_max_chars=80000`, `max_videos_per_run=20` (LLM 호출 회수 상한), `skip_shorts=true (duration<90s)`, `timezone="Asia/Seoul"`.

## Output Formats

### 영상별 MD (frontmatter)

`00_Wiki/CLAUDE.md` 필수 5필드 + 도메인 4필드:

```yaml
---
source_url: https://www.youtube.com/watch?v={video_id}
source_type: youtube
captured_at: 2026-05-07T07:14:32+09:00
tier: T3                        # watchlist_hits 있으면 T3, 없으면 T2
tags: [youtube, aekyung_invest, 005930, NVDA]
video_id: dQw4w9WgXcQ
channel: aekyung_invest
watchlist_hits: ["005930", "NVDA"]
was_truncated: false
---
```

본문 구조:
```markdown
# {video_title}

> {channel_name} · {published_at_kst} · [원본]({url})

## 3줄 헤드라인
- ...
- ...
- ...

## 🎯 핵심 인사이트
- ...
- ...
- ...

## 🚨 레드팀 시각 (반대 관점·리스크·의문점)
- ...
- ...

## 📊 종목 영향
### 워치리스트 hit
- **삼성전자 (005930)** — 긍정적 / 신뢰도 high
  - 근거: ...
  - 인용: "..."
### 자동 발견 종목
- ...
```

### 일일 브리핑 MD

`00_Wiki/youtube/_daily/{YYYY-MM-DD}_brief.md` 본문 구조:
1. **🎯 오늘의 시장 read** (3-5문장)
2. **핵심 인사이트** (영상들 종합, 3-5 불릿)
3. **🚨 레드팀 시각** (오늘 영상들의 합의에 대한 반론·리스크, 2-4 불릿)
4. **📊 워치리스트 ticker rollup** (표: symbol · 순방향 · 언급 영상 수 · 영상별 한 줄)
5. **🔍 자동 발견 종목** (별도 섹션)
6. **📺 오늘 영상 목록** (링크)

### Telegram 메시지 (3블록 구조 강제)

per_video 포맷 (≤4096B; 초과 시 `domain/telegram_format.py`가 문장 경계 분할 + `(1/2)` + `reply_to_message_id` 연결):
```
📺 {channel_name} — {video_title}
🔗 {url}
🕐 {published_at_kst}

🎯 핵심 인사이트
• {insight_1}
• {insight_2}
• {insight_3}

🚨 레드팀 시각
• {counter_1}
• {counter_2}

📊 종목 영향 ({watchlist_hits 또는 "자동 발견 N개"})
• {symbol_or_name} {direction_emoji} {direction_label} — {one_line_reason}
• ...

📝 vault: {md_path_relative}
```

direction_emoji 매핑: 긍정적 🟢 / 중립 ⚪ / 부정적 🔴 / 언급만 ◽

daily 포맷:
```
📅 {YYYY-MM-DD} 일일 시장 브리핑

🎯 오늘의 시장 read
{market_read 1-2 문장 헤드라인}

🔑 핵심 인사이트
• ...

🚨 레드팀 시각
• ...

📊 워치리스트 종목별 영향
• 삼성전자 (005930) 🟢 긍정적 — 3개 영상 언급
• NVDA 🔴 부정적 — 2개 영상 (혼조 1)
• ...

📺 오늘 처리 영상 {N}건
{video_link_list}
```

## LLM Invocation (`_clients/llm.py`)

**API 키 미사용**. `claude` CLI를 subprocess로 호출하여 사용자의 Claude Code 로그인을 활용.

호출 형태:
```python
result = subprocess.run(
    [config.claude_bin, "-p",
     "--model", config.claude_model,            # 'sonnet' 등
     "--output-format", "json",                  # 구조화 응답
     "--permission-mode", "bypassPermissions",   # 자동 실행 (Bash 등 허용 안 됨, prompt 응답만)
     "--max-turns", "1"],                        # 단일 턴 제한
    input=prompt,                                 # stdin으로 prompt 전달
    capture_output=True,
    text=True,
    timeout=config.claude_timeout_sec,
)
```

응답 파싱: `result.stdout`을 JSON으로 파싱 → `result["result"]` (모델 텍스트) → 본문에서 fenced code block (` ```json ... ``` `) 추출 → `VideoAnalysis` 스키마로 검증.

프롬프트 설계 (`prompts/system_video_analysis.ko.md`):
- 역할 정의: "한국 회계감사인을 위한 시장 분석가. 영상 내용을 종합하되, 영상 화자의 thesis에 맹목적으로 동조하지 말 것"
- 입력: transcript (필요 시 truncated) + watchlist YAML 직렬화 + 영상 메타
- 출력 스키마(JSON, fenced): `{ headline_3line[3], key_insights[3-5], red_team[2-4], tickers[{symbol|null, display, in_watchlist, direction, reasoning, quotes[0-2], confidence}], watchlist_hits[symbols] }`
- **레드팀 강제**: "key_insights를 3-5개 도출 후, 각각에 대한 반대 시각·리스크·약점·의문점을 통합해 red_team 2-4건으로 응축. red_team이 비어 있으면 응답 거부 (영상이 단순 사실 보도여서 반론할 게 없으면 그 사실을 red_team[0]에 명시)"
- 음슴체 사용 안 함 (감사 의견 아님). 한국어 평이체.

Daily brief 프롬프트 (`prompts/system_daily_brief.ko.md`):
- 입력: 당일 모든 `VideoAnalysis` 직렬화
- 출력: `{ market_read, key_insights[3-5], red_team[2-4], ticker_rollup[{symbol, display, in_watchlist, net_direction, mention_count, per_video[]}] }`
- red_team은 영상들이 합의하는 thesis에 대한 반론

대안 검토:
- **Claude Agent SDK (Python)**: 공식 패키지. subprocess보다 안정적이지만 의존성 추가. → 후속 ADR로 마이그레이션 검토. MVP는 subprocess로 단순 시작.
- `claude -p --output-format stream-json`: 스트리밍 응답. 단일 호출에는 필요 없음. → 미채택.

검증:
- `claude --version` 동작 확인을 `config.py` 로드 시 1회
- 첫 run 전 `claude -p "ping" --output-format json` 헬스체크

## Idempotency & State

**JSON state 파일** (gitignored Sink): `~/vault/Harness/sink/youtube_market_brief/state.json`

```json
{
  "version": 1,
  "videos": {
    "<video_id>": {
      "processed_at": "2026-05-07T07:14:32+09:00",
      "channel_id": "UCxxx",
      "outcome": "ok | skipped_no_caption | failed",
      "md_path": "00_Wiki/youtube/aekyung_invest/2026-05-07__title.md"
    }
  },
  "daily": { "2026-05-07": { "brief_sent": true, "brief_path": "..." } },
  "last_run": "2026-05-07T07:15:00+09:00"
}
```

쓰기는 atomic: tempfile → `os.replace()`. SQLite/MD 스캔은 기각(MVP 과함, frontmatter 파싱 비용).

## Error Handling Policy

핵심 규칙: **per-video try/except, run-level continue** (PAS 실패 격리 계약).

| 단계 | 실패 시 동작 | 재시도 |
|---|---|---|
| Discover (YouTube API 429/5xx) | exp backoff 60s/240s/600s | 3회 |
| Discover 403 quotaExceeded | graceful checkpoint + Telegram alert + abort run | 0 |
| Transcribe `no_captions` | video skip, state `skipped_no_caption` (영구) | 0 |
| Transcribe `api_changed` (yt-transcript-api 내부 변경) | video skip + state `failed` + 일일 1회 critical alert (50%+ 실패율) | 0 |
| Analyze (claude CLI exit ≠ 0 / timeout) | exp backoff 30s/120s/300s | 3회 |
| Analyze 응답 JSON 스키마 위반 | "JSON only, fenced code block" 강조 + red_team/key_insights 필수 명시 1회 재시도 → skip + dump (`Harness/sink/youtube_market_brief/dumps/{video_id}.txt`) | 1회 |
| Analyze `red_team` 빈 배열 | 1회 재시도 (프롬프트 강조). 그래도 빈 경우 — 강제 한 줄 "(영상이 단편 사실 보도, 별도 반론 없음)" 채워 통과 |
| Aggregate 실패 | per-video MD는 정상, daily만 partial 실패 → Telegram alert | 1회 |
| Notify (Telegram) 실패 | log only, run 계속 | 1회 |

호출 회수 ceiling: 처리된 video 수 ≥ `max_videos_per_run`(기본 20) 시 다음 video analyze 호출 전 abort + Telegram alert + 미처리 video는 다음 run에 자연 처리(state 미기록). 비용은 사용자의 Claude Code 사용량(별도 청구 없음)으로 흡수되므로 USD 기반 cap 대신 호출 회수 cap 사용.

로그: `~/vault/Harness/logs/youtube_market_brief/{YYYY-MM-DD}.log` (KST 날짜).

## Top Edge Cases

| # | 시나리오 | 처리 |
|---|---|---|
| E1 | 오늘 신규 0건 | per-video/daily/Telegram 모두 skip; `RunReport.discovered=0` 로그만 |
| E3 | transcript ≫ context window | head 60% + tail 30% + middle 10% 균등 샘플 단일 호출, frontmatter `was_truncated: true`, 본문 상단 ⚠ 경고 |
| E5 | Telegram > 4096자 | 문장/개행 경계로 분할, hard cap 4000자, `reply_to_message_id`로 연결 |
| E6 | handle(@xxx)만 입력 | 첫 run에 `channels.search.list`로 1회 resolve → `channels.yaml` 자동 갱신 |
| E7 | watchlist ticker 충돌 ("삼성"이 인사말로 등장) | `quotes` 필수, 빈/짧으면 hit 제외; LLM 프롬프트에 "맥락상 의미 있는 언급만" 명시 |
| E8 | quota 중간 소진 | 처리분만 state.json flush, 잔여는 다음 run |
| E9 | watchlist 빈 파일 | analyze는 정상, auto-discovery only, 모든 영상 T2, stderr 1회 안내 |
| E10 | Shorts (<90초) | `skip_shorts=true`로 skip |
| E11 | Live/Premiere 진행 중 | 현재 run skip, state 미기록 → 다음 run에서 종료 후 재처리 |
| E13 | 같은 ticker 영상 내 긍/부 모순 | `direction`은 단일이지만 `reasoning` 양면 + `confidence="medium"` → rollup `혼조` |
| E16 | 같은 날 cron 재실행 | state로 video skip; daily MD 존재 시 미덮어씀(`--force` 토글), Telegram daily 재발송 안 함 |

## Phased Execution (Codex Handoff)

각 phase는 **수용 기준 = verifiable command**. Phase 완료 시 Codex가 `docs/adr/{NNNN}-{title}.md`에 종료 보고.

### Phase 0 — Scaffold + Config + ADR
- 디렉토리 트리 + `pyproject.toml`(uv) + `.env.example` + `config/*.example` + ADR-0001/0002 + skeleton CLI
- ✅ `uv run python -m youtube_market_brief --help` exit 0
- ✅ `pytest -q` collected 0, exit 0

### Phase 1 — Discovery + Transcript
- `_clients/youtube_data.py`, `_clients/transcript.py`, `pipeline/discover.py`, `pipeline/transcribe.py`, `domain/slugify.py`, `state/store.py`, CLI `discover`/`transcribe`
- ✅ 실제 채널 1개 (env 있을 때) 최신 영상 list 출력
- ✅ handle → channel_id 자동 resolve 동작 (E6)
- ✅ no_captions → TranscriptSkip 반환 (E2)
- ✅ fake client 단위테스트 통과

### Phase 2 — LLM Analyzer + Watchlist
- `_clients/llm.py` (`claude` CLI subprocess wrapper + JSON 파싱 + 헬스체크)
- `prompts/system_video_analysis.ko.md` — `red_team` 강제 지시 포함
- `pipeline/analyze.py`, `domain/watchlist.py`
- ✅ `uv run ymb health` → claude CLI 동작 확인 ("ping" 호출 응답)
- ✅ fixture transcript → `VideoAnalysis` snapshot 3건 통과
- ✅ **응답에 `key_insights` 3-5개 + `red_team` 2-4개 + `tickers[]` 모두 포함됨 검증**
- ✅ 충돌 가드(E7), 빈 watchlist(E9) 단위테스트 통과
- ✅ 스키마 위반 응답 fixture에 대해 1회 재시도 후 skip + dump 동작

### Phase 3 — Markdown Writer + Idempotency
- `domain/markdown.py`, `pipeline/write_video.py`, `state/store.py` 마무리
- ✅ golden file diff 통과 (한국어 frontmatter sort_keys 안정)
- ✅ tier 결정 로직(watchlist hits 유무) 단위테스트
- ✅ atomic write — 중간 예외 주입 시 state.json 비파괴

### Phase 4 — Daily Aggregator
- `domain/daily_brief.py`, `pipeline/aggregate.py`, `prompts/system_daily_brief.ko.md`
- ✅ 3 fixture VideoAnalysis → DailyBrief 골든 일치
- ✅ rollup 수학 검증 (긍/긍/부 → `혼조`)
- ✅ 영상 0건일 때 daily 미생성 (E1)

### Phase 5 — Telegram Notifier
- `_clients/telegram.py`(`dry_run`), `domain/telegram_format.py`, `pipeline/notify.py`
- ✅ `DRY_RUN=true` → `Harness/sink/youtube_market_brief/telegram_dryrun/{ts}.txt` 작성
- ✅ 4500자 메시지 → 2개 분할, (1/2) 표기, 코드블록/인용 경계 보존

### Phase 6 — CLI Orchestrator + Harness Runner YAML
- `orchestrator.py`, CLI `run`/`run --date`/`run --video-url`/`run --dry-run`/`run --force`
- `~/vault/Harness/runners/youtube_market_brief.yaml`
- ✅ `uv run ymb run --dry-run --date 2026-05-06` E2E (실 채널/영상 + 실 LLM + Telegram dryrun)
- ✅ 재실행 시 모든 video skip, daily 재발송 안 함
- ✅ runner YAML이 `wiki_evaluator.yaml` 스키마와 정합
- ✅ 실패 격리 — 1 video에 예외 주입해도 나머지 정상 처리

### Phase 7 — End-to-End Smoke
- `tests/test_e2e_smoke.py`, ADR 종료 보고 (plan vs 산출 차이 / 잔여 작업 / 검증 결과)
- ✅ 1 channel + 1 video 실데이터 + `--dry-run` E2E 통과
- ✅ HANDOFF.md 검증기준 1~4 모두 충족

## Risks & Mitigations

| # | 리스크 | 잠금 |
|---|---|---|
| H1 | youtube-transcript-api 내부 변경 → transcript 0건 | 버전 핀 + 일일 실패율 50%+ 시 critical Telegram alert + 후속 ADR로 yt-dlp fallback 예약 |
| H3 | `claude` CLI 호출이 헤드리스(cron)에서 인증 실패할 수 있음 | (a) Phase 2 수용 기준에 `ymb health` 명령 명시 — 실 cron 환경에서 1회 검증 필수; (b) cron 실행 시 `HOME`, `PATH`가 필요한 인증 디렉토리(`~/.claude/`) 접근 가능하도록 wrapper 스크립트 추가; (c) claude CLI 인증 만료 감지 시 Telegram critical alert |
| H10 | `claude -p` 호출 응답에 추가 텍스트(설명·인사말)가 섞여 JSON 파싱 실패 | 프롬프트에 "JSON only, fenced ```json ... ``` 외 어떤 텍스트도 출력 금지" 강조. 1회 재시도. 그래도 실패 시 정규식으로 첫 fenced block 추출 시도 |
| H11 | 호출 회수 ceiling 도달 — 영상 많은 날 일부 누락 | 누락분 다음 day cron에서 자연 catch-up (state 미기록). 1주 운영 후 `max_videos_per_run` 캘리브레이션 |
| H2 | handle resolve quota | 1회 resolve 후 `channels.yaml` 자동 영구 기록 |
| H4 | truncation으로 후반부 손실 | MVP head/tail 샘플링 + 경고. map-reduce는 후속 ADR |
| H5 | 영상 많은 날 cost cap 걸림 | 누락분 다음 날 자연 catch-up; 1주 캘리브레이션 권고 |
| H7 | UTC vs KST 시간대 | `RunReport.date`는 KST. tz-aware datetime 강제. 시간대 단위테스트 1건 |
| H8 | auto-discovery false positive | `quotes` 필수 + watchlist 미포함 ticker는 daily 별도 섹션, 메인 시장 read에 미포함 |

## Verification (E2E)

설정 파일 작성 후:
```bash
cd ~/vault/01_Projects/01_youtube_market_brief
uv sync
cp .env.example .env && vim .env                 # YOUTUBE_API_KEY + TELEGRAM_BOT_TOKEN/CHAT_ID 채움 (Anthropic 키 불필요)
uv run ymb health                                 # claude CLI 동작/인증 확인
cp config/channels.yaml.example config/channels.yaml && vim config/channels.yaml
cp config/watchlist.yaml.example config/watchlist.yaml && vim config/watchlist.yaml

uv run ymb run --dry-run --date 2026-05-06       # 실 LLM/YouTube 호출, Telegram만 dry
# 검증 항목:
#  - 00_Wiki/youtube/{channel}/2026-05-06__*.md 생성 + frontmatter 5+4필드
#  - 00_Wiki/youtube/_daily/2026-05-06_brief.md 생성
#  - Harness/sink/youtube_market_brief/telegram_dryrun/{ts}.txt 생성
#  - Harness/sink/youtube_market_brief/state.json 갱신 (videos[*], daily.{date}.brief_sent)
#  - Harness/logs/youtube_market_brief/2026-05-06.log 작성

uv run ymb run --dry-run --date 2026-05-06       # 재실행 — 모든 video skip, daily 재발송 안 됨
uv run ymb run --date 2026-05-06                 # Telegram 실 발송
uv run pytest -q                                 # 전체 테스트 통과
```

스케줄 등록(검증 통과 후): `~/vault/Harness/runners/youtube_market_brief.yaml`이 PAS Runner 인프라에 의해 cron으로 실행되도록 등록(launchd/cron 후속 작업; PAS의 schedule trigger 처리 방식에 맞춤).

## Critical Files

신규 생성:
- `~/vault/01_Projects/01_youtube_market_brief/CLAUDE.md`, `CONTEXT.md`, `HANDOFF.md`, `README.md`
- `~/vault/01_Projects/01_youtube_market_brief/docs/adr/0001-module-structure.md`
- `~/vault/01_Projects/01_youtube_market_brief/docs/adr/0002-idempotency-state.md`
- `~/vault/01_Projects/01_youtube_market_brief/plans/2026-05-07-initial-plan.md` (본 plan 사본)
- `~/vault/01_Projects/01_youtube_market_brief/src/youtube_market_brief/orchestrator.py`
- `~/vault/01_Projects/01_youtube_market_brief/src/youtube_market_brief/domain/types.py`
- `~/vault/01_Projects/01_youtube_market_brief/src/youtube_market_brief/pipeline/{discover,transcribe,analyze,write_video,aggregate,notify}.py`
- `~/vault/01_Projects/01_youtube_market_brief/src/youtube_market_brief/_clients/{youtube_data,transcript,llm,telegram}.py`
- `~/vault/01_Projects/01_youtube_market_brief/src/youtube_market_brief/state/store.py`
- `~/vault/01_Projects/01_youtube_market_brief/prompts/{system_video_analysis,system_daily_brief}.ko.md`
- `~/vault/01_Projects/01_youtube_market_brief/config/{channels,watchlist}.yaml.example`
- `~/vault/01_Projects/01_youtube_market_brief/.env.example`
- `~/vault/01_Projects/01_youtube_market_brief/pyproject.toml`
- `~/vault/Harness/runners/youtube_market_brief.yaml`

기존 갱신:
- `~/vault/03_Resources/Idea_Backlog.md` — 본 아이디어 행 추가 + 상태 "승격"
- `~/vault/AGENTS.md` "Active Projects" 목록에 `01_youtube_market_brief` 추가

## Reused Infrastructure (재사용)

- **Runner YAML 스키마**: [`~/vault/Harness/runners/wiki_evaluator.yaml`](~/vault/Harness/runners/wiki_evaluator.yaml) 형식 그대로 차용 (`name`, `trigger.{type,cron,timezone}`, `inputs`, `agent`, `outputs`, `idempotency`, `notification`)
- **Frontmatter 컨벤션**: [`~/vault/00_Wiki/CLAUDE.md`](~/vault/00_Wiki/CLAUDE.md) 필수 5필드 (`source_url`, `source_type`, `captured_at`, `tier`, `tags`) + Tier 규칙 매핑
- **Codex 인계 템플릿**: [`~/vault/01_Projects/00_personal_agent_system/HANDOFF.md`](~/vault/01_Projects/00_personal_agent_system/HANDOFF.md) 그대로 복사
- **프로젝트 시스템 컨텍스트 형식**: [`~/vault/01_Projects/00_personal_agent_system/CLAUDE.md`](~/vault/01_Projects/00_personal_agent_system/CLAUDE.md) 형식 모델
- **Ubiquitous Language 시드**: [`~/vault/01_Projects/00_personal_agent_system/CONTEXT.md`](~/vault/01_Projects/00_personal_agent_system/CONTEXT.md)의 용어 재사용 (Runner, Trigger=Schedule, Sink, Logs, Tier, Ingestion)
- **Sink/Logs 위치 컨벤션**: `~/vault/Harness/sink/`, `~/vault/Harness/logs/` (gitignored, PAS와 동일)
- **Python 환경**: pyenv 3.12.7 + uv + pytest (PAS 결정 그대로)
- **`claude` CLI**: 사용자 Claude Code 로그인을 그대로 활용 (별도 API 키·청구 없음). Phase 2에서 `claude -p --output-format json` 패턴 검증

## Out of Scope (MVP 비범위)

- Whisper ASR fallback (transcript 비공개 영상 자동 전사) — H1 모니터링 결과 따라 후속 ADR로 결정
- Map-reduce chunking (긴 영상 청크 합성) — H4 모니터링 결과 따라 후속 ADR로 결정
- 자동 발견 ticker의 symbol 자동 해상도 (예: "엔비디아" → "NVDA" 매핑) — display name만 보존
- Web UI / dashboard — vault MD가 곧 UI
- 다중 사용자 / 다중 chat_id — 단일 사용자 가정
- 영상 처리 우선순위 큐잉 — FIFO (published_at 오름차순)
