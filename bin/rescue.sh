#!/bin/bash
# rescue.sh — 로컬 자동 fallback runner.
#
# 트리거 조건: Drive에 오늘(KST) 일일 브리핑 MD가 없거나, brief.md는 있지만
# state.json의 daily.{TODAY}.brief_sent != true이면 로컬에서 ymb run 실행 후
# 결과를 Drive로 push.
# launchd `com.kjun.ymb-rescue.plist`가 매일 KST 08:30 + RunAtLoad로 호출.

set -uo pipefail

PROJECT_DIR="/Users/kjun/vault/01_Projects/01_youtube_market_brief"
VAULT_ROOT="/Users/kjun/vault"
DRIVE_REMOTE="vault"
DRIVE_ROOT_ID="1SbXHMkHBpBluAYydhDNVLcgjxSipYLjI"
RCLONE_FLAGS=(--drive-root-folder-id "$DRIVE_ROOT_ID" --quiet)

export PATH="/opt/homebrew/bin:/usr/local/bin:/Users/kjun/.nvm/versions/node/v24.15.0/bin:$PATH"

LOG_DIR="$VAULT_ROOT/Harness/logs/youtube_market_brief"
mkdir -p "$LOG_DIR"
TODAY=$(TZ=Asia/Seoul date +%Y-%m-%d)
LOG_FILE="$LOG_DIR/rescue_${TODAY}.log"
STATE_DIR="$VAULT_ROOT/Harness/sink/youtube_market_brief"
STATE_FILE="$STATE_DIR/state.json"

log() { echo "$(TZ=Asia/Seoul date '+%Y-%m-%dT%H:%M:%S%z') [rescue] $*" | tee -a "$LOG_FILE"; }

# .env에서 Telegram 자격 추출 (수동 발송 알림용 — ymb run 자체 발송과 별개).
TELEGRAM_BOT_TOKEN=$(grep -E '^TELEGRAM_BOT_TOKEN=' "$PROJECT_DIR/.env" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'")
TELEGRAM_CHAT_ID=$(grep -E '^TELEGRAM_CHAT_ID=' "$PROJECT_DIR/.env" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'")

notify_failure() {
    local reason="$1"
    local msg="[YMB-rescue ${TODAY}] 실패: ${reason}
log: ${LOG_FILE}"
    if [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && [ -n "${TELEGRAM_CHAT_ID:-}" ]; then
        curl -s --max-time 10 -X POST \
            "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
            --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" \
            --data-urlencode "text=${msg}" \
            >/dev/null 2>&1 || log "telegram notify also failed"
    else
        log "WARN: TELEGRAM creds 없음 — 알림 skip"
    fi
}

log "start today=$TODAY"

# 1. cloud가 갖고 있는 state.json을 로컬로 pull.
#    (skip 판정과 멱등성 둘 다 사용)
mkdir -p "$STATE_DIR"
rclone copy "${DRIVE_REMOTE}:Harness/sink/youtube_market_brief/state.json" \
    "$STATE_DIR/" \
    "${RCLONE_FLAGS[@]}" 2>>"$LOG_FILE" || log "no remote state.json — using local"

# 2. skip 판정: Drive brief 존재 AND state.json brief_sent==true 둘 다 만족 시.
BRIEF_NAME="${TODAY}_brief.md"
brief_present="no"
brief_sent="no"

if rclone lsf "${DRIVE_REMOTE}:00_Wiki/youtube/_daily/" "${RCLONE_FLAGS[@]}" 2>>"$LOG_FILE" | grep -qx "$BRIEF_NAME"; then
    brief_present="yes"
fi

if [ -f "$STATE_FILE" ]; then
    sent=$(python3 -c "import json,sys
try:
    d=json.load(open('$STATE_FILE'))
    print('yes' if d.get('daily',{}).get('$TODAY',{}).get('brief_sent') is True else 'no')
except Exception:
    print('no')" 2>/dev/null || echo "no")
    brief_sent="$sent"
fi

log "skip-check brief_present=$brief_present brief_sent=$brief_sent"

if [ "$brief_present" = "yes" ] && [ "$brief_sent" = "yes" ]; then
    log "skip: drive brief + state.brief_sent 둘 다 OK (cloud succeeded)"
    exit 0
fi

if [ "$brief_present" = "yes" ] && [ "$brief_sent" = "no" ]; then
    log "drive에 brief.md 있으나 state.brief_sent != true — Telegram 발송 누락 가능. rescue 진행"
fi

log "proceeding with local rescue"

# 3. ymb run.
log "running ymb (cli mode)"
cd "$PROJECT_DIR" || {
    log "cd failed"
    notify_failure "rescue.sh: cd $PROJECT_DIR 실패"
    exit 1
}
if uv run ymb run >>"$LOG_FILE" 2>&1; then
    log "ymb run ok"
else
    rc=$?
    log "ymb run FAILED rc=$rc"
    notify_failure "ymb run rc=$rc (cli mode)"
    exit "$rc"
fi

# 4. 결과를 Drive로 push.
log "pushing outputs to drive"
push_failed=""
rclone copy "$VAULT_ROOT/00_Wiki/youtube/" "${DRIVE_REMOTE}:00_Wiki/youtube/" "${RCLONE_FLAGS[@]}" 2>>"$LOG_FILE" || {
    log "drive push (00_Wiki) failed"
    push_failed="00_Wiki"
}
rclone copy "$STATE_FILE" \
    "${DRIVE_REMOTE}:Harness/sink/youtube_market_brief/" \
    "${RCLONE_FLAGS[@]}" 2>>"$LOG_FILE" || {
    log "drive push (state) failed"
    push_failed="${push_failed:+$push_failed,}state"
}

if "$VAULT_ROOT/Harness/scripts/sync_market_insights_to_drive.sh" >>"$LOG_FILE" 2>&1; then
    log "market insights mobile sync ok"
else
    log "market insights mobile sync failed"
    push_failed="${push_failed:+$push_failed,}market_insights"
fi

if [ -n "$push_failed" ]; then
    notify_failure "Drive push 실패: $push_failed (로컬 발송은 완료, 다음 회차 cloud가 stale state pull할 수 있음)"
fi

log "done"
