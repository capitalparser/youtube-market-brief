# ADR-0005: claude CLI subprocess → Anthropic API + cloud cron 실행

- 상태: Superseded by ADR-0007
- 날짜: 2026-05-08

## 배경

ADR-0001~0004까지의 결정은 "사용자 맥북에서 `claude` CLI subprocess로 LLM 호출"을 전제했다. 근거:

- 별도 Anthropic API 키 발급/billing 회피
- 사용자 Claude Code 로그인 세션 재활용
- vault Runner 패턴(`~/vault/Harness/runners/`)과의 일관성

이 전제는 **맥북이 켜져 있을 때만 동작**한다는 제약을 만든다. 운영상 다음 시나리오에서 깨진다:

- 맥북이 닫혀 있는 시각(취침, 외출, 이동 등)에는 cron이 실행되지 않음
- 출장/여행으로 며칠 닫혀 있으면 그 기간 영상이 모두 누락
- 사용자 의도(매일 KST 07:00 일일 브리핑)를 일관되게 충족하지 못함

사용자는 "맥북 닫혀 있어도 텔레그램으로 받아보는 것"을 원한다. → cloud cron 필요. cloud runner는 `claude` CLI 인증 세션을 가질 수 없으므로 LLM 호출 경로 자체를 바꿔야 한다.

## 결정

1. **LLM 클라이언트 이중 구현**:
   - `ClaudeCLIClient`: 기존 (subprocess). 로컬 전용. 유지.
   - `AnthropicAPIClient`: 신규 (Anthropic Messages API SDK). cloud-runnable. 기본값.
   - 둘 다 동일한 `LLMClient` Protocol 만족 → 호출부 무변경.
   - `LLM_PROVIDER` env (`api` | `cli`)로 선택. 기본 `api`.

2. **모델**: `claude-sonnet-4-6`. 기존 `--model sonnet` 의도 보존 (ADR-0001 기조). Opus 4.7도 가능하나 비용·인텔리전스 trade-off상 Sonnet 유지.

3. **Prompt caching**: 시스템 프롬프트에 `cache_control: ephemeral` 부착. per-video 호출이 같은 system을 반복 사용하므로 1회차 이후 캐시 히트 (입력 토큰 비용 ~10% 수준). `system_video_analysis.ko.md`(~7KB) 만 최소 캐시 임계(2048 tokens) 충족. 일일 브리핑 프롬프트(~3KB)는 미달이라 캐싱 안 됨 — 정상.

4. **Cloud 실행 인프라** (`.github/workflows/digest.yml`):
   - Cron `0 22 * * *` UTC = KST 07:00.
   - `VAULT_ROOT_PATH`로 vault 경로를 GH Actions runner 임시 디렉토리(`$GITHUB_WORKSPACE/_cloud_vault`)로 라우팅.
   - rclone + Google Drive 서비스 계정으로 입력(state, config) 다운로드 + 출력(MD, state) 업로드.
   - Drive Desktop이 사용자 로컬에 vault MD를 동기화 → 결과적으로 vault에 반영됨 (간접 sync).

5. **state.json은 Drive에 유지**. cloud run 시작 시 download → 종료 시 upload. 멱등성 유지.

6. **Telegram 발송은 cloud에서 직접 수행**. dry-run mode는 cloud에서 미사용.

## 대안

- **A. 로컬 cron + 맥 항상 켜짐**: 코드 변경 없음. 사용자 라이프스타일 제약 (불수용).
- **B. Self-hosted runner (Mac mini, Pi, VPS)**: `claude` CLI 그대로. 인프라 비용 + 인증 휘발 이슈 (Claude Code 로그인이 풀리면 작업 중단).
- **C. cloud cron + state를 GH 레포에 commit**: Drive 의존성 없음. 단 매 run마다 commit 발생 → 히스토리 노이즈, 동시성 충돌 가능. 사용자가 Drive를 이미 쓰고 있어 일관성 떨어짐.
- **D. Drive API를 Python 코드 안에서 직접 호출**: Python에 Drive 종속. 향후 다른 스토리지(S3, R2 등)로 갈아탈 때 코드 수정 필요. 외부 sync(rclone) 분리가 더 유연.

C, D 모두 합리적이지만 사용자가 명시적으로 Drive를 선택했고 (Personal_AI_DB 인프라와 일관) Python을 vault-pure로 유지하려는 설계 원칙(ADR-0001) 때문에 (D)도 기각.

## 결과

- 신규 의존성: `anthropic>=0.45.0` (Python). rclone (workflow 런타임).
- 신규 GH Secrets:
  - `ANTHROPIC_API_KEY` — Anthropic Messages API 키
  - `YOUTUBE_API_KEY` — YouTube Data API v3
  - `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` — 발송 대상
  - `GDRIVE_SERVICE_ACCOUNT_JSON` — Google Cloud 서비스 계정 키 (JSON 전체)
  - `GDRIVE_OUTPUT_FOLDER_ID` — Drive 폴더 ID (서비스 계정에 Editor 권한 부여 필요)
- 비용 영향: Sonnet 4.6 + 캐싱 적용 시 영상 1건 ≈ $0.003~0.005, 일 20영상 ≈ 월 $5 미만. Cloud 인프라 비용 0 (GH Actions free tier).
- 운영 리스크:
  - **Drive 폴더 권한 누수**: 서비스 계정 JSON이 GH secret으로 들어가지만, Drive 폴더 ID가 secret에서 빠지면 노출 가능. 폴더는 서비스 계정에만 공유되고 외부 링크 없음을 사전 확인.
  - **API 키 비용 폭증**: cron 빈도 + 영상 수 + max_tokens 곱 → 예상치 못한 비용. `MAX_VIDEOS_PER_RUN=20`으로 캡됨.
  - **state.json 동시성**: cloud cron과 로컬 manual run이 같은 시각에 돌면 conflict. workflow `concurrency.group=digest`로 cloud 측은 직렬화. 로컬 측은 사용자 책임 (드물 것).

## 추후 고려

- 로컬에서도 cloud workflow와 같은 state.json을 공유하려면 로컬 cron도 Drive sync 필요. 현재는 Phase 외.
- Anthropic API 토큰 비용 모니터링은 별도 dashboard 미구축. usage 정보는 `LLMResponse.raw_envelope["usage"]`에 포함되므로 향후 누적/리포트 가능.
- `claude-sonnet-4-6` → `claude-opus-4-7` 승격은 단일 환경변수(`ANTHROPIC_MODEL`) 변경만으로 가능 (코드 무변경).
