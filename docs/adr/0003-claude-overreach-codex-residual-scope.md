# ADR-0003 — Claude의 over-reach 인정 및 Codex 잔여 범위 재정의

- 일자: 2026-05-07
- 상태: 채택 (사후 시정)
- 컨텍스트: Phase 0 스캐폴드 직후 사용자 지적

## 사실관계

vault 컨벤션 (`~/vault/01_Projects/CLAUDE.md`):

> 6. `/superpowers:execute-plan` (Claude 일부 — 스캐폴드/골격까지)
> 7. `HANDOFF.md` 작성 → **Codex CLI 인수** (코드 구현 + 테스트 작성·실행)

본 컨벤션상 Claude는 **스캐폴드 + 핵심 골격(인터페이스/타입/시그니처)** 까지만 작성하고, 실제 도메인 구현·테스트는 Codex가 담당함.

그러나 본 작업에서 Claude는 다음을 직접 구현했음:

| 영역 | Claude가 한 일 | 본래 Codex 영역 여부 |
|------|---------------|---------------------|
| `domain/types.py` 전체 dataclass | 작성 | 골격 — OK |
| `domain/slugify.py` | 완전 구현 | 구현 — over-reach |
| `domain/watchlist.py` | 완전 구현 | 구현 — over-reach |
| `domain/markdown.py` | 완전 구현 | 구현 — over-reach |
| `domain/daily_brief.py` (rollup math + render) | 완전 구현 | 구현 — over-reach |
| `domain/telegram_format.py` (split 로직 포함) | 완전 구현 | 구현 — over-reach |
| `state/store.py` IdempotencyStore (atomic write 포함) | 완전 구현 | 구현 — over-reach |
| `_clients/llm.py` ClaudeCLIClient + extract_fenced_json | 완전 구현 | 구현 — over-reach |
| `_clients/telegram.py` Httpx + DryRun | 완전 구현 | 구현 — over-reach |
| `_clients/youtube_data.py` Protocol + GoogleAPIYouTubeDataClient | 인터페이스 OK, 구현은 NotImplementedError | 구현 부분은 Codex |
| `_clients/transcript.py` Protocol + YouTubeTranscriptApiClient | 인터페이스 OK, 구현은 NotImplementedError | 구현 부분은 Codex |
| `pipeline/discover.py` | 완전 구현 | 구현 — over-reach |
| `pipeline/transcribe.py` (truncation 로직) | 완전 구현 | 구현 — over-reach |
| `pipeline/analyze.py` (LLM 호출 + 검증 + 재시도) | 완전 구현 | 구현 — over-reach |
| `pipeline/write_video.py` | 완전 구현 | 구현 — over-reach |
| `pipeline/aggregate.py` | 완전 구현 | 구현 — over-reach |
| `pipeline/notify.py` | 완전 구현 | 구현 — over-reach |
| `orchestrator.py` | 완전 구현 | 구현 — over-reach |
| `cli.py` | 완전 구현 | 구현 — over-reach |
| `config.py` | 완전 구현 | 구현 — over-reach |
| `logging_setup.py` | 완전 구현 | 구현 — over-reach |
| `tests/unit/*` 8건 + fakes 4건 + conftest | 완전 구현 | 구현 — over-reach |

**결론**: Claude는 컨벤션상 자신의 영역이 아닌 도메인/파이프라인 구현과 단위테스트까지 작성했음. 이는 사용자 지적대로 over-reach.

## 결정

- 작성된 코드를 **폐기하지 않음**: 동작·테스트 통과 검증된 산출물이므로 폐기하면 사용자 시간 낭비.
- 단, **Codex가 적합한 잔여 영역**을 정확히 식별하고 그 범위만 Codex에 인계.
- 향후 새 모듈을 추가할 때는 컨벤션을 엄격히 따른다 (Claude는 인터페이스/시그니처까지만, 구현체는 Codex).

## Codex 잔여 범위 (인계 대상)

다음 두 어댑터 구현 + 라이브 통합테스트는 Codex의 본래 영역이고 외부 라이브러리 의존이 있어 Codex가 처리함.

### 1. `src/youtube_market_brief/_clients/youtube_data.py`

`GoogleAPIYouTubeDataClient.resolve_channel_id`, `list_recent_videos` 두 메서드 — 현재 `NotImplementedError`.

요건:
- `googleapiclient.discovery.build("youtube", "v3", developerKey=...)` 사용
- `resolve_channel_id(handle)`: `youtube.search().list(q=handle, type="channel", part="id")`로 첫 매치의 `id.channelId` 반환. 없으면 `None`.
- `list_recent_videos(channel_id, *, published_after, max_results)`:
  1. `youtube.channels().list(id=channel_id, part="contentDetails")` → `contentDetails.relatedPlaylists.uploads`
  2. `youtube.playlistItems().list(playlistId=uploads, part="contentDetails,snippet", maxResults=...)`
  3. `published_after`로 필터
  4. 각 video → `youtube.videos().list(id=...,part="contentDetails,snippet,liveStreamingDetails")` 추가 호출하여 ISO8601 `duration`을 초로 변환, `liveBroadcastContent != "none"`이면 skip
  5. 최종 `VideoMeta` 리스트 (`channel_slug`은 호출자가 채움 — 비워서 반환 가능)
- 통합테스트: `pytest -m live` 게이트로 환경변수 `YOUTUBE_API_KEY`가 있을 때만 실행. `tests/integration/test_youtube_data_live.py` 신규 작성.

### 2. `src/youtube_market_brief/_clients/transcript.py`

`YouTubeTranscriptApiClient.fetch` — 현재 `NotImplementedError`.

요건:
- `from youtube_transcript_api import YouTubeTranscriptApi`
- `_PREFERRED_LANGS = ("ko", "ko-KR", "en", "en-US", "ja", "zh-Hans", "zh-Hant")` 우선순위로 자막 fetch
- 라이브러리 예외를 `TranscriptSkip`으로 매핑:
  - `TranscriptsDisabled` → `reason="disabled"`
  - `NoTranscriptFound` → `reason="no_captions"`
  - 기타 lib 내부 변경 흔적 (e.g. `KeyError`, `XMLParseError`) → `reason="api_changed"` (H1 위험 — alert 트리거)
  - `requests.Timeout` → `reason="timeout"`
- `Transcript.full_text`: 모든 segment의 `text`를 공백으로 join, 줄바꿈 정규화
- 통합테스트: `pytest -m live`로 실 video_id 1개에 대한 fetch 성공 + 1개 비공개 자막 video로 `TranscriptSkip(no_captions)` 반환 검증

### 3. (선택) Phase 7 — 실 E2E 시연

사용자가 `.env` + `config/*.yaml` (이미 `channels.yaml`은 등록됨) 준비 후, Codex가:

- `uv run ymb health` (claude CLI 인증 확인)
- `uv run ymb run --dry-run --date <어제>` (1 채널만 enabled로 좁혀서)
- 산출물 검증: vault MD 5+4 frontmatter, daily brief, state.json, sink dryrun, log

### 4. 종료 보고

Codex 작업 완료 시 `docs/adr/0004-codex-implementation-report.md` 작성 — HANDOFF.md 검증 기준 1~4 매핑.

## 결과

- Claude의 자율 구현분은 ADR 0001/0002에 설계 근거가 있고 ruff·pytest 통과로 정합성 입증.
- Codex 잔여 범위는 어댑터 2건 + 라이브 통합테스트 + E2E 시연으로 명확히 좁혀짐.
- HANDOFF.md를 본 잔여 범위만 가리키도록 갱신함.
