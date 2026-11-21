#!/bin/bash
# Weekly off-GitHub mirror backup for the BuyersForce repo, with a traffic-light result.
#
# Pushes a full mirror (--mirror) of every branch/tag to a second, separate
# remote named "backup-mirror" -- insurance against the main "origin" GitHub
# repo/account being deleted, compromised, or corrupted. Run every Sunday 4pm
# by launchd (com.buyersforce.githubmirror). Does not need Claude, only this
# Mac and its saved GitHub login. It does NOT use the Mail app: on YELLOW or
# RED it shows a Mac notification. The emails for yellow/red come from the
# Sunday ~5pm Pacific cloud check (Gmail), which also writes the weekly log entry.
#
# Result, one of:
#   GREEN  - pushed on the first try AND the backup repo's main matches this
#            repo's main. Nothing to do.
#   YELLOW - pushed fine, but with a hiccup (needed a retry, or the last good
#            backup was more than 9 days ago, i.e. a week was missed). A Mac
#            notification is shown.
#   RED    - the push failed twice, or the copy doesn't match. A Mac
#            notification is shown.
#
# Files (all in _local_backups/, which is gitignored):
#   mirror_backup.log      - full history of every run
#   mirror_status.txt      - one line: the latest result
#   mirror_last_ok.txt     - unix time of the last GREEN/YELLOW run
#
# Test the notification without pushing anything:  bash scripts/ops/mirror_backup.sh --test-alert
set -uo pipefail
export PATH="/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin"
export GIT_TERMINAL_PROMPT=0
cd "$(dirname "$0")/../.." || exit 1
mkdir -p _local_backups

LOG="_local_backups/mirror_backup.log"
STATUS="_local_backups/mirror_status.txt"
LAST_OK="_local_backups/mirror_last_ok.txt"
STALE_DAYS=9

log() { echo "$*" >> "$LOG"; }
now_utc() { date -u +%Y-%m-%dT%H:%M:%SZ; }

send_alert() {  # $1 = title, $2 = message. A Mac notification only -- never the Mail app.
  if /usr/bin/osascript - "$1" "$2" >> "$LOG" 2>&1 <<'APPLESCRIPT'
on run argv
  display notification (item 2 of argv) with title (item 1 of argv)
end run
APPLESCRIPT
  then
    log "ALERT: Mac notification shown ($1)"
  else
    log "ALERT: could not show a Mac notification ($1)"
  fi
}

# finish <GREEN|YELLOW|RED> <plain-English summary>
finish() {
  local color="$1" summary="$2" stamp
  stamp="$(now_utc)"
  echo "$color | $stamp | $summary" > "$STATUS"
  log "RESULT: $color -- $summary"
  if [ "$color" != "GREEN" ]; then
    local todo="Probably nothing -- it went through. Check _local_backups/mirror_backup.log if it keeps happening."
    [ "$color" = "RED" ] && todo="The backup did NOT complete. Open Claude Code in the BuyersForce repo and ask Claude to check the weekly GitHub mirror."
    send_alert "BuyersForce weekly GitHub mirror: $color" "$summary $todo"
  fi
  [ "$color" = "RED" ] && exit 1
  exit 0
}

log "=== $(now_utc) starting mirror backup ==="

if [ "${1:-}" = "--test-alert" ]; then
  send_alert "BuyersForce weekly GitHub mirror: TEST (ignore)" "This is a test of the Mac alert notification."
  exit 0
fi

if ! git remote get-url backup-mirror >/dev/null 2>&1; then
  finish RED "no 'backup-mirror' remote is configured in the repo."
fi

LOCAL_MAIN="$(git rev-parse refs/heads/main 2>/dev/null || true)"
if [ -z "$LOCAL_MAIN" ]; then
  finish RED "could not find a local 'main' branch to back up."
fi

# A dated marker tag rides along in the mirror, so the backup repo itself shows when each run happened.
RUN_TAG="mirror-run-$(date +%Y-%m-%d)"
git tag -f "$RUN_TAG" "$LOCAL_MAIN" >> "$LOG" 2>&1

ATTEMPTS=0
PUSHED=0
while [ "$ATTEMPTS" -lt 2 ] && [ "$PUSHED" -eq 0 ]; do
  ATTEMPTS=$((ATTEMPTS + 1))
  [ "$ATTEMPTS" -gt 1 ] && { log "first push failed; waiting 60s, then retrying"; sleep 60; }
  if git push backup-mirror --mirror >> "$LOG" 2>&1; then PUSHED=1; fi
done

if [ "$PUSHED" -eq 0 ]; then
  git tag -d "$RUN_TAG" >> "$LOG" 2>&1
  finish RED "the push to GitHub failed twice in a row (see the log for the exact error)."
fi

REMOTE_MAIN="$(git ls-remote backup-mirror refs/heads/main 2>>"$LOG" | cut -f1)"
if [ "$REMOTE_MAIN" != "$LOCAL_MAIN" ]; then
  finish RED "the push reported success, but the backup repo's main (${REMOTE_MAIN:-missing}) does not match this repo's main (${LOCAL_MAIN:0:7})."
fi

# Passed. Look for reasons to downgrade GREEN to YELLOW.
HICCUPS=""
[ "$ATTEMPTS" -gt 1 ] && HICCUPS="the first push attempt failed and the retry worked. "
if [ -f "$LAST_OK" ]; then
  LAST="$(cat "$LAST_OK" 2>/dev/null || echo 0)"
  AGE_DAYS=$(( ( $(date +%s) - LAST ) / 86400 ))
  [ "$AGE_DAYS" -gt "$STALE_DAYS" ] && HICCUPS="${HICCUPS}the previous good backup was $AGE_DAYS days ago, so at least one week was missed. "
fi
date +%s > "$LAST_OK"

REFS="$(git ls-remote backup-mirror 2>/dev/null | wc -l | tr -d ' ')"
if [ -n "$HICCUPS" ]; then
  finish YELLOW "mirror is up to date (main = ${LOCAL_MAIN:0:7}, $REFS refs), but ${HICCUPS}"
fi
finish GREEN "mirror pushed; backup main = ${LOCAL_MAIN:0:7} (matches), $REFS refs."
