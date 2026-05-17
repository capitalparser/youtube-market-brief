---
name: "source-command-ymb"
description: "YMB 파이프라인 수동 실행 (uv run ymb run)"
---

# source-command-ymb

Use this skill when the user asks to run the migrated source command `ymb`.

## Command Template

프로젝트 루트 `/Users/kjun/vault/01_Projects/01_youtube_market_brief`에서 `uv run ymb run`을 실행해줘.

규칙:
- Bash 호출 시 `(cd /Users/kjun/vault/01_Projects/01_youtube_market_brief && uv run ymb run)` 형태로 절대 경로 사용. `cd`로 세션 cwd를 바꾸지 말 것.
- 실행 출력은 요약하지 말고 그대로 보여줘 (RunReport 라인 포함).
- 비정상 종료 시 exit code, 마지막 50줄 로그, 가장 그럴듯한 원인 한 줄 요약.
- 정상 종료 시 다음을 한 줄씩 보고:
  - 처리된 video 수 / skip 수 / fail 수 (RunReport에서 추출)
  - 일일 brief 생성 여부 + 경로
  - Telegram 발송 성공 여부

이 슬래시는 cron/launchd 자동 실행과 별개인 수동 트리거임. state.json 멱등성에 의해 같은 video는 자동으로 skip됨.
