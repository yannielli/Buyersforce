#!/bin/bash
# Weekly off-GitHub mirror backup for the BuyersForce repo, with a traffic-light result.
#
# Pushes a full mirror (--mirror) of every branch/tag to a second, separate
# remote named "backup-mirror" -- insurance against the main "origin" GitHub
# repo/account being deleted, compromised, or corrupted. Run every Sunday 4pm
# by launchd (com.buyersforce.githubmirror). Does not need Claude, only this
# Mac, its saved GitHub login, and (for alerts) the Mail app.
#
# Result, one of:
#   GREEN  - pushed on the first try AND the backup repo's main matches this
#            repo's main. Nothing to do.
#   YELLOW - pushed fine, but with a hiccup (needed a retry, or the last good
#            backup was more than 9 days ago, i.e. a week was missed). An
#            email goes to kj.jackson9@gmail.com.
#   RED    - the push failed twice, or the copy doesn't match. An email goes
#            to kj.jackson9@gmail.com.
#
# Files (all in _local_backups/, which is gitignored):
#   mirror_backup.log      - full history of every run
#   mirror_status.txt      - one line: the latest result
#   mirror_last_ok.txt     - unix time of the last GREEN/YELLOW run
#
# Test the email without pushing anything:  bash scripts/ops/mirror_backup.sh --test-alert
set -uo pipefail
export PATH="/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin"
export GIT_TERMINAL_PROMPT=0
cd "$(dirname "$0")/../.." || exit 1
mkdir -p _local_backups

LOG="_local_backups/mirror_backup.log"
STATUS="_local_backups/mirror_status.txt"
LAST_OK="_local_backups/mirror_last_ok.txt"
ALERT_TO="kj.jackson9@gmail.com"
STALE_DAYS=9

log() { echo "$*" >> "$LOG"; }
now_utc() { date -u +%Y-%m-%dT%H:%M:%SZ; }

send_alert() {  # $1 = subject, $2 = body
  if /usr/bin/osascript - "$ALERT_TO" "$1" "$2" >> "$LOG" 2>&1 <<'APPLESCRIPT'
on run argv
  set theTo to item 1 of argv
  set theSubject to item 2 of argv
  set theBody to item 3 of argv
  tell application "Mail"
    set msg to make new outgoing message with properties {subject:theSubject, content:theBody, visible:false}
    tell msg to make new to recipient at end of to recipients with properties {address:theTo}
    send msg
  end tell
end run
APPLESCRIPT
  then
    log "ALERT email sent to $ALERT_TO"
  else
    log "ALERT email FAILED to send (Mail app problem) -- showing a Mac notification instead"
    /usr/bin/osascript -e "display notification \"$1\" with title \"BuyersForce mirror backup\"" >> "$LOG" 2>&1
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
    [ "$color" = "RED" ] && todo="The backup did NOT complete. Open Claude Code in the BuyersForce repo and say: the weekly GitHub mirror backup failed -- here is the email."
    send_alert "BuyersForce weekly GitHub mirror: $color" \
"Status: $color
When: $stamp (UTC)

What happened: $summary

What to do: $todo"
  fi
  [ "$color" = "RED" ] && exit 1
  exit 0
}

log "=== $(now_utc) starting mirror backup ==="

if [ "${1:-}" = "--test-alert" ]; then
  send_alert "BuyersForce weekly GitHub mirror: TEST (ignore)" "This is a test of the alert email. If you can read it, YELLOW and RED alerts will reach you."
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
