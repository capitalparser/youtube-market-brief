# ADR-0007 — OpenAI cloud LLM + sidecar-first aggregation

- 날짜: 2026-05-17
- 상태: 채택

## 배경

ADR-0005는 cloud cron을 위해 Anthropic Messages API와 `claude-sonnet-4-6`를 채택한다고 기록했다. 이후 실제 구현은 OpenAI SDK 기반 `OpenAIAPIClient`와 GitHub Actions의 `OPENAI_MODEL=gpt-4.1`로 이동했다. 운영 코드는 정상 동작하지만 ADR, AGENTS.md, README의 LLM 설명이 서로 달라져 비용 추정, 모델 특성, 장애 진단 기준이 흐려졌다.

또한 07:00 KST daily brief 재구성은 vault Markdown을 regex로 파싱해 LLM에 다시 넘겼다. 영상별 `.analysis.json` sidecar가 이미 canonical 구조 데이터를 담고 있으므로, Markdown parsing은 불필요하게 취약한 Interface가 됐다.

## 결정

1. Cloud 기본 LLM provider는 `OpenAIAPIClient`로 고정한다.
   - `LLM_PROVIDER=api`는 OpenAI Chat Completions API를 사용한다.
   - GitHub Actions 기본 모델은 `OPENAI_MODEL=gpt-4.1`이다.
   - `LLM_PROVIDER=cli`의 `ClaudeCLIClient`는 로컬 수동 실행용 adapter로 유지한다.

2. Daily aggregation은 sidecar-first로 동작한다.
   - `aggregate-only`는 `{YYYY-MM-DD}__*.analysis.json` per-video sidecar를 먼저 읽는다.
   - sidecar가 있으면 typed `VideoAnalysis`를 복원해 기존 `aggregate_daily` 경로를 사용한다.
   - sidecar가 없을 때만 기존 Markdown parsing fallback을 사용한다.

3. State retry 정책은 terminal skip과 transient skip을 구분한다.
   - `no_captions`, `disabled`, `geo_blocked`는 재발견 대상에서 제외한다.
   - `ip_blocked`, `api_changed`, `timeout`은 다음 run에서 재시도한다.

4. Per-video 처리 흐름은 `pipeline/video_processing.py` Module에 집중한다.
   - orchestrator와 `collect-urls` CLI가 같은 Module을 호출한다.
   - transcribe/analyze/write/notify/state checkpoint 정책을 한곳에서 유지한다.

## 결과

- 모델/비용/장애 진단 기준은 OpenAI cloud path를 기준으로 본다.
- Daily Brief의 ticker rollup은 Markdown 문자열이 아니라 sidecar의 ticker 구조 데이터에서 계산된다.
- 영구 no-caption 영상은 반복 재시도하지 않고, 클라우드 IP 차단 같은 일시 장애는 자동 재시도된다.
- Weekly rollup은 daily ticker sector metadata를 보존해 sector별 related tickers를 채울 수 있다.

## 후속 고려

- OpenAI Responses API 또는 structured output으로 이동하면 fenced JSON parsing을 줄일 수 있다.
- LLM 사용량은 `LLMResponse.raw_envelope["usage"]`에 이미 들어오므로, run report에 비용/토큰 누적을 추가할 수 있다.
