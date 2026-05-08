# HANDOFF.md — Codex CLI Handoff Guide

## 사전 통지: Claude over-reach 사실

본 프로젝트는 Phase 0 직후 Claude가 컨벤션을 어기고 도메인/파이프라인 구현과 단위테스트까지 작성한 상태로 인계됨. 사용자가 이를 지적하여 ADR-0003에 기록함.

**Codex는 src/와 tests/를 처음부터 다시 짓는 것이 아니라, ADR-0003에서 식별된 잔여 범위(외부 어댑터 2건 + 라이브 통합테스트 + E2E 시연)만 처리한다.**

기존 산출물은 ruff + pytest(37건) 통과 상태이므로 폐기하지 말 것. 다만 Codex가 잔여 범위 작업 중에 기존 코드의 결함을 발견하면 ADR-0004 종료 보고에 명시할 것.

## 당신(Codex)에게

이 프로젝트는 Claude가 설계와 계획을, Codex가 코드 구현과 테스트를 담당하는 분담 모델로 운영된다. 본 파일은 Claude → Codex 인수 시점의 표준 안내다.

## 입력

다음 파일들을 순서대로 읽고 작업하라.

1. `CONTEXT.md` — 도메인 사전 (Ubiquitous Language)
2. `CLAUDE.md` — 프로젝트 시스템 컨텍스트, 인터페이스 계약, 기준 결정
3. `docs/adr/0001-module-structure.md`, `0002-idempotency-state.md` — 설계 근거
4. **`docs/adr/0003-claude-overreach-codex-residual-scope.md` — 본 인계의 실제 작업 범위 (반드시 먼저 읽을 것)**
5. `plans/2026-05-07-initial-plan.md` — 전체 plan (참고용)

## 작업 범위

ADR-0003 §"Codex 잔여 범위"에 정의됨. 요약:

1. `src/youtube_market_brief/_clients/youtube_data.py` — `GoogleAPIYouTubeDataClient.resolve_channel_id` / `list_recent_videos` 구현 (현 상태 `NotImplementedError`)
2. `src/youtube_market_brief/_clients/transcript.py` — `YouTubeTranscriptApiClient.fetch` 구현 (현 상태 `NotImplementedError`)
3. 위 두 어댑터에 대한 라이브 통합테스트 (`pytest -m live` 게이트, env 있을 때만)
4. (선택) Phase 7 E2E 시연 — `uv run ymb run --dry-run` 실 1 채널/1 영상

## 출력 위치

- 코드: `src/` (위 두 파일만 수정. 다른 파일 수정은 ADR로 사전 제안 후 사용자 승인)
- 테스트: `tests/integration/test_youtube_data_live.py`, `tests/integration/test_transcript_live.py` 신규
- 종료 보고 ADR: `docs/adr/0004-codex-implementation-report.md`

## 작업 원칙

- **Plan 충실 이행**: 가장 최신 plan의 acceptance criteria를 우선. Plan에 없는 일을 추가하지 말 것 (필요하면 ADR로 제안 후 사용자 승인).
- **테스트 동시 작성**: 함수/클래스 추가 시 같은 PR로 테스트 추가.
- **외부 의존 격리**: API/네트워크/파일시스템 호출은 인터페이스로 추상화하여 모킹 가능하게.
- **실패 격리 + 멱등성**: `CLAUDE.md` 인터페이스 계약 참조.
- **커밋 단위**: 한 커밋에 한 가지 의도. 메시지는 한국어 또는 영어 일관되게.

## 검증 기준

1. plan Phase 1 + Phase 7 acceptance criteria 충족 (Phase 2~6은 이미 Claude over-reach로 구현 완료, 동작 확인 필요 시 fake 기반 단위테스트 결과 참조)
2. 두 어댑터에 대한 통합테스트 작성, `pytest -q` 기존 37건 + 신규 통합테스트 모두 통과
3. `CONTEXT.md` Ubiquitous Language 일관성 유지 (Channel/Video/Transcript/Tier 등 용어 그대로)
4. 실제 채널 1건 (`config/channels.yaml`에 사전 등록됨: `@hkglobalmarket`, `@MK_Invest`, `@kpunch`) + 실제 video 1건으로 `ymb run --dry-run` E2E 동작 확인

## 종료 보고

작업 완료 시 `docs/adr/{NNNN}-{title}.md`에 다음 항목 기록:

- 무엇을 구현했나 (plan 대비 차이)
- 어떤 결정을 했나 (plan에서 위임된 세부 결정)
- 무엇이 남았나 (후속 작업 제안)
- 검증 결과 (테스트 통과 수, 실제 시연 결과)

이후 Claude가 plan vs 산출물 정합성 리뷰를 진행한다.

## 환경

- Python 3.12.7 (pyenv) + uv (`uv sync --extra dev` 완료된 상태)
- Git 2.54
- 작업 디렉토리: `~/vault/01_Projects/01_youtube_market_brief/`
- 외부 도구 호출 시 `~/vault/Harness/runners/{이름}.yaml`에 정의된 명령만 사용
- LLM은 `claude` CLI subprocess 호출 (Anthropic API 키 미사용)
- 외부 라이브러리: `google-api-python-client`, `youtube-transcript-api` (이미 의존성 설치됨)

---

_이 템플릿은 신규 프로젝트 스캐폴드 시 `promote_idea` runner가 그대로 복사하여 배포한다._
