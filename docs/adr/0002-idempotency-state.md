# ADR-0002 — Idempotency State Store

- 일자: 2026-05-07
- 상태: 채택
- 컨텍스트: Phase 0 스캐폴드

## 결정

영상 처리 idempotency를 단일 JSON 파일로 관리한다.

- 위치: `~/vault/Harness/sink/youtube_market_brief/state.json`
- gitignored (Sink는 git 추적 제외 — `.gitignore` 검증됨)
- 쓰기는 atomic: tempfile에 쓴 뒤 `os.replace()`
- PK: `video_id`

## 스키마

```json
{
  "version": 1,
  "videos": {
    "<video_id>": {
      "processed_at": "2026-05-07T07:14:32+09:00",
      "channel_id": "UCxxx",
      "outcome": "ok | skipped_no_caption | failed",
      "skip_reason": "no_captions | disabled | geo_blocked | api_changed | ip_blocked | timeout | null",
      "md_path": "00_Wiki/youtube/aekyung_invest/2026-05-07__title.md"
    }
  },
  "daily": {
    "2026-05-07": {
      "brief_sent": true,
      "brief_path": "00_Wiki/youtube/_daily/2026-05-07_brief.md"
    }
  },
  "last_run": "2026-05-07T07:15:00+09:00"
}
```

## 대안

- **MD 파일명에서 video_id 역추적**: 파일명에 video_id 미포함(slug 기반). frontmatter 파싱 필요 → I/O 비효율 + 부분 실패 시 재처리 가능성. 기각.
- **SQLite**: MVP 과함. PAS의 다른 Sink는 JSON/MD로 충분. 향후 모듈 5개 이상 누적 시 통합 검토. 기각.
- **JSON state 파일 (현 결정)**: 단순, 투명, atomic write. 수동 inspection 가능. 채택.

## 결과

- 동일 video_id 재투입 시 skip 가능
- terminal caption skip(`no_captions`, `disabled`, `geo_blocked`)은 완료 처리하고 transient skip(`ip_blocked`, `api_changed`, `timeout`)은 다음 실행에서 재시도
- daily brief 재생성 방지 (`daily.{date}.brief_sent`)
- 부분 실패 후 재실행 시 처리분만 skip — 잔여는 정상 처리
- atomic write로 process kill 시에도 state 비파괴
