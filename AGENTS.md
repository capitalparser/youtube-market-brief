# 01_youtube_market_brief — Project System Context

본 프로젝트는 사용자가 큐레이션한 YouTube 채널들의 신규 영상에서 시장·종목 정보를 매일 자동 추출해 vault에 정리하고 Telegram으로 발송한다. ~/vault/01_Projects/00_personal_agent_system(PAS)의 Runner 인프라를 사용하는 첫 도메인 Runner이다.

## 컴포넌트 책임

| 컴포넌트 | 책임 | 위치 |
|---------|------|------|
| Discover | YouTube Data API v3로 채널의 신규 영상 메타데이터 수집 | `src/.../pipeline/discover.py` |
| Transcribe | youtube-transcript-api로 자막 추출 | `src/.../pipeline/transcribe.py` |
| Analyze | `LLMClient` Protocol 호출 → 영상별 요약·핵심 인사이트·레드팀 분석·종목 영향 | `src/.../pipeline/analyze.py` |
| Watchlist | 사용자 watchlist YAML과 LLM 발견 ticker 매칭·충돌 가드 | `src/.../domain/watchlist.py` |
| Write Video | 영상별 MD를 `00_Wiki/youtube/{channel}/...`에 작성 | `src/.../pipeline/write_video.py` |
| Aggregate | 당일 분석들을 합성해 일일 브리핑 MD 생성 | `src/.../pipeline/aggregate.py` |
| Notify | Telegram Bot API로 영상 단위 + 일일 브리핑 발송 | `src/.../pipeline/notify.py` |
| State Store | video_id idempotency JSON 저장소 | `src/.../state/store.py` |
| Video Processing | 영상 1건의 transcribe/analyze/write/notify/state checkpoint 공통 처리 | `src/.../pipeline/video_processing.py` |
| Orchestrator | 위를 조립, 실패 격리, RunReport 생성 | `src/.../orchestrator.py` |
| Runner YAML | cron 스케줄 메타 (PAS Harness가 실행) | `~/vault/Harness/runners/youtube_market_brief.yaml` |

## 인터페이스 계약

- `_clients/*`는 모두 `typing.Protocol` 인터페이스 노출. 구현은 동일 파일 또는 별도 클래스.
- `pipeline/*`은 client를 인자로 받음 (DI). 전역 싱글턴 금지.
- `domain/*`은 client-free deterministic. 외부 호출/IO 없음.
- 모든 외부 의존(YouTube API, transcript backends, LLM APIs/CLI, Telegram Bot API)은 `_clients/`로 격리.
- 출력 MD frontmatter 필수 5필드 (PAS Wiki 컨벤션): `source_url, source_type, captured_at, tier, tags`.
- 영상별 MD는 도메인 4필드 추가: `video_id, channel, watchlist_hits, was_truncated`.
- Capture Depth 결정: `watchlist_hits` 비면 `light`, 있으면 `deep` (`00_Wiki/AGENTS.md` 매핑). frontmatter 필드 `tier` 값으로 소문자 기록.

## Codex 인수 시 주의사항

- `src/` 변경 시 동일 모듈 단위로 `tests/`에 테스트 추가/갱신
- 외부 의존은 인터페이스로 격리, 테스트는 in-memory fake 사용 (`tests/fakes/`)
- 실패 격리: 한 video 실패가 전체 run을 막지 않음 (per-video try/except)
- 멱등성: 동일 video_id 재투입 시 skip (`state/store.py`). 단 `ip_blocked`, `api_changed`, `timeout` 같은 transient transcript skip은 다음 실행에서 재시도.
- 입력 검증과 출력 검증 분리 (한 함수에 섞지 말 것)

## 기준 결정 (현 시점)

- Python 3.12.7 (pyenv) + `uv` 의존 관리
- 테스트: `pytest`. 통합 테스트 우선. 라이브 client 테스트는 `pytest -m live` 게이트.
- 저장 포맷: Markdown + YAML frontmatter (Obsidian 호환)
- LLM: 기본 `OpenAIAPIClient` (`LLM_PROVIDER=api`, cloud runnable). 로컬 필요 시 `ClaudeCLIClient` (`LLM_PROVIDER=cli`) 사용.
- 시간대: KST (`Asia/Seoul`). RunReport.date는 KST 기준.
- 출력 위치: `~/vault/00_Wiki/youtube/{channel_slug}/{YYYY-MM-DD}__{video_slug}.md` + `_daily/{YYYY-MM-DD}_brief.md`.
- 스케줄: KST 07:00 / 12:00 / 18:00 / 23:00. Daily Brief는 07:00에 전일 sidecar/MD 기준으로 재구성.
- 호출 회수 cap: `max_videos_per_run=20` (영상 많은 날은 다음 day 자연 catch-up).

## 비범위 (MVP)

- 항상 활성화되는 ASR fallback (현재는 `ENABLE_STT_FALLBACK=true`일 때만 OpenAI STT 최후 fallback)
- Map-reduce chunking (긴 영상 청크 합성)
- 자동 발견 ticker symbol 자동 해상도
- 다중 사용자 / 다중 chat_id

---

_See also: `CONTEXT.md` (도메인 사전), `HANDOFF.md` (Codex 인수), `plans/2026-05-07-initial-plan.md` (실행 plan)_
