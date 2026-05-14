#!/usr/bin/env bash
# Fire-and-forget wrapper called from Claude Code hooks (Stop /
# SessionStart) and from launchd. Returns immediately so the hook
# never blocks the user.
#
# Forks one of:
#   bin/pipeline-run.sh --sid <session-id>     (new 3-layer pipeline, default)
#   bin/refresh.sh                              (legacy monolith;
#                                                set CLAUDE_WORKTREE_LEGACY_PIPELINE=1)
#
# Also captures the current Claude Code session's terminal location
# (Zellij/tmux pane) into cache/session_locations.json — used by the
# HTML UI to jump back to the right pane.

set -u

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# Platform-aware log location.
if [ "$(uname)" = "Darwin" ]; then
  LOG="$HOME/Library/Logs/claude-code-worktree.log"
else
  LOG="${XDG_STATE_HOME:-$HOME/.local/state}/claude-code-worktree/refresh.log"
fi
mkdir -p "$(dirname "$LOG")"

# Slurp the hook stdin once. Both record-location.py (for pane info)
# and pipeline-run.sh (for the session_id) need it. The hook delivers
# JSON like {"session_id": "...", "cwd": "...", "source": "Stop"}.
PAYLOAD="$(cat 2>/dev/null || true)"

# Extract session_id from the payload (best-effort).
SID=$(printf '%s' "$PAYLOAD" | python3 -c "
import json, sys
try:
    d = json.loads(sys.stdin.read())
    sid = d.get('session_id') or ''
    print(sid)
except Exception:
    pass
" 2>/dev/null || echo "")

# Record the terminal location for this session. Re-feeds the payload
# to record-location.py via stdin so it can read the same fields.
printf '%s' "$PAYLOAD" | python3 "$REPO_ROOT/bin/record-location.py" 2>>"$LOG" || true

# Fork the actual work and detach so the hook returns immediately.
(
  echo "[hook] $(date -Iseconds) refresh-bg fired (pid=$$, sid=${SID:-?})" >> "$LOG"

  if [ "${CLAUDE_WORKTREE_LEGACY_PIPELINE:-}" = "1" ]; then
    # Legacy single-process refresh (kept for one bake-in week per
    # DD-002 §10.1 Phase 5).
    bash "$REPO_ROOT/bin/refresh.sh" >> "$LOG" 2>&1
  else
    # New pipeline: Layer 0 → Layer 1 (this session) → Layer 2 coalesce
    if [ -n "$SID" ]; then
      bash "$REPO_ROOT/bin/pipeline-run.sh" --sid "$SID" >> "$LOG" 2>&1
    else
      # No session_id in payload — happens for some launchd triggers
      # or stdin-less invocations. Fall back to all-dirty sweep, which
      # is a no-op in steady state (mtime check skips already-summarized
      # sessions).
      bash "$REPO_ROOT/bin/pipeline-run.sh" --all-dirty >> "$LOG" 2>&1
    fi
  fi

  echo "[hook] $(date -Iseconds) refresh-bg finished" >> "$LOG"
) </dev/null >/dev/null 2>&1 &

disown 2>/dev/null || true
exit 0
