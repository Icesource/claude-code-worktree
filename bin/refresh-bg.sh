#!/usr/bin/env bash
# Fire-and-forget wrapper for refresh.sh, intended for Claude Code hooks.
# Returns immediately so it never blocks the Stop/SessionStart hook.
# Uses an atomic mkdir lock (portable, no flock) to prevent overlapping runs.

set -u

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOCK_DIR="$REPO_ROOT/cache/refresh.lock.d"
LOG="$HOME/Library/Logs/claude-mindmap.log"

mkdir -p "$REPO_ROOT/cache"
mkdir -p "$(dirname "$LOG")"

(
  # Atomic lock: mkdir succeeds only if directory doesn't exist.
  if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    # Stale lock cleanup: if lock is older than 10 minutes, remove and retry.
    if [ -d "$LOCK_DIR" ]; then
      lock_age=$(( $(date +%s) - $(stat -f %m "$LOCK_DIR" 2>/dev/null || echo 0) ))
      if [ "$lock_age" -gt 600 ]; then
        rm -rf "$LOCK_DIR"
        mkdir "$LOCK_DIR" 2>/dev/null || exit 0
      else
        echo "[$(date -Iseconds)] refresh already running, skip" >> "$LOG"
        exit 0
      fi
    fi
  fi
  trap 'rm -rf "$LOCK_DIR"' EXIT

  echo "[$(date -Iseconds)] refresh triggered" >> "$LOG"
  bash "$REPO_ROOT/bin/refresh.sh" >> "$LOG" 2>&1
  echo "[$(date -Iseconds)] refresh done" >> "$LOG"
) </dev/null >/dev/null 2>&1 &

disown 2>/dev/null || true
exit 0
