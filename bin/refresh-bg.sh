#!/usr/bin/env bash
# Fire-and-forget wrapper for refresh.sh, intended for Claude Code hooks.
# Returns immediately so it never blocks the Stop/SessionStart hook.
#
# Concurrency is handled inside refresh.sh itself (mkdir-based lock), so
# this wrapper just forks and detaches.

set -u

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG="$HOME/Library/Logs/claude-mindmap.log"

mkdir -p "$(dirname "$LOG")"

(
  echo "[$(date -Iseconds)] refresh-bg invoked" >> "$LOG"
  bash "$REPO_ROOT/bin/refresh.sh" >> "$LOG" 2>&1
  echo "[$(date -Iseconds)] refresh-bg finished" >> "$LOG"
) </dev/null >/dev/null 2>&1 &

disown 2>/dev/null || true
exit 0
