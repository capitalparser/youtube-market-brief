# ADR-0004 — Codex 구현 종료 보고

- 일자: 2026-05-08
- 상태: 완료
- 컨텍스트: ADR-0003 Codex 잔여 범위 구현

## 무엇을 구현했나

- `GoogleAPIYouTubeDataClient.resolve_channel_id`
  - `googleapiclient.discovery.build("youtube", "v3", developerKey=...)` lazy-init 구현.
  - `YOUTUBE_API_KEY`가 비어 있으면 `ValueError("YOUTUBE_API_KEY required")` 발생.
  - YouTube Data API `search().list(...)` 첫 결과의 `id.channelId` 반환.
- `GoogleAPIYouTubeDataClient.list_recent_videos`
  - 채널 uploads playlist 조회 후 `playlistItems().list(...)`로 후보 영상 조회.
  - `published_after` 기준 필터링.
  - `videos().list(...)` batch 호출로 duration, snippet, live 상태 조회.
  - 라이브 콘텐츠를 제외하고 `VideoMeta` 리스트를 발행시각 오름차순으로 반환.
- `YouTubeTranscriptApiClient.fetch`
  - `youtube-transcript-api` import/API 버전 차이를 흡수하는 transcript list 호출 구현.
  - 한국어, 영어, 일본어, 중국어 우선순위 후 사용 가능한 임의 transcript fallback 구현.
  - `Transcript` segment/full_text 구성 및 `TranscriptSkip` 예외 매핑 구현.
- 라이브 통합테스트 2개 파일 추가.

## 어떤 결정을 했나

- YouTube duration 파싱은 새 의존성 없이 `_DUR_RE` 기반 helper로 구현했다.
- `published_after`는 비교 안정성을 위해 UTC aware datetime으로 정규화한다.
- `youtube-transcript-api`는 설치 버전에 따라 `YouTubeTranscriptApi.list_transcripts(video_id)` 또는 `YouTubeTranscriptApi().list(video_id)`를 사용한다.
- 라이브 테스트는 기존 `pyproject.toml`의 `live` marker 정책을 그대로 따른다.

## 무엇이 남았나

- `pytest -m live`는 실제 네트워크, YouTube API quota, 공개 자막 상태에 의존하므로 CI에서는 별도 secret/env 게이트가 필요하다.
- Phase 7 E2E dry-run 시연은 이번 요청의 필수 명령 목록에는 없어서 실행하지 않았다.

## 검증 결과

- `UV_CACHE_DIR=.uv-cache uv sync`: 성공. 단, dev extra 없이 동기화되어 `pytest`, `ruff` 등 optional dev tools가 제거됨.
- `UV_CACHE_DIR=.uv-cache uv run pytest -q`: 실패. `pytest` executable 없음.
- `UV_CACHE_DIR=.uv-cache uv run ruff check src/ tests/`: 실패. `ruff` executable 없음.
- `UV_CACHE_DIR=.uv-cache uv sync --extra dev`: 실패. sandbox network/DNS 제한으로 `pytest-asyncio==1.3.0` wheel 다운로드 불가.
- `python -m pytest -q`: 실패. active Python environment에 `pytest` 없음.
- `python -m ruff check src/ tests/`: 실패. active Python environment에 `ruff` 없음.
- `UV_CACHE_DIR=.uv-cache uv run python -m compileall -q src tests`: 성공.
- `UV_CACHE_DIR=.uv-cache uv run python` smoke check:
  - `_parse_iso_duration_sec("PT1H2M3S") == 3723`
  - `parse_iso8601_published(...)` UTC aware 확인
  - invalid transcript id가 `TranscriptSkip`으로 반환됨 확인

요청된 `37+ passed 0 failed` 확인은 현재 sandbox의 network 제한과 `uv sync`의 dev extra 제거 때문에 완료하지 못했다.

## 발견한 결함

- `uv sync`만 실행하면 optional dev dependencies가 빠져 검증 명령(`pytest`, `ruff`)이 실행 불가 상태가 된다. 개발 검증 환경에서는 `uv sync --extra dev` 또는 동일 효과의 dev dependency 설치가 필요하다.
