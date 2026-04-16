#!/usr/bin/env bash
# Uninstall claude-code-worktree: remove slash commands, shell wrapper,
# Claude Code hooks, and macOS LaunchAgent.
set -euo pipefail

HOME_DIR="$HOME"
OS="$(uname)"

echo "Uninstalling claude-code-worktree..."
echo

# 1. Slash commands
for cmd in mindmap mindmap-refresh; do
  link="$HOME_DIR/.claude/commands/$cmd.md"
  if [ -L "$link" ] || [ -f "$link" ]; then
    rm "$link"
    echo "[1/4] removed slash command: /$cmd"
  fi
done

# 2. Shell wrapper
BIN_LINK="$HOME_DIR/.local/bin/mindmap"
if [ -L "$BIN_LINK" ] || [ -f "$BIN_LINK" ]; then
  rm "$BIN_LINK"
  echo "[2/4] removed shell wrapper: $BIN_LINK"
else
  echo "[2/4] shell wrapper not found, skipping"
fi

# 3. Claude Code hooks
SETTINGS="$HOME_DIR/.claude/settings.json"
if [ -f "$SETTINGS" ]; then
  cp "$SETTINGS" "$SETTINGS.bak.$(date +%s)"
  python3 - "$SETTINGS" <<'PY'
import json, sys
path = sys.argv[1]
data = json.load(open(path))
hooks = data.get("hooks", {})
removed = 0
for event in list(hooks.keys()):
    before = len(hooks[event])
    hooks[event] = [
        e for e in hooks[event]
        if not any(
            "refresh-bg.sh" in h.get("command", "")
            and ("claude-code-worktree" in h["command"] or "claude-mindmap" in h["command"])
            for h in e.get("hooks", [])
        )
    ]
    removed += before - len(hooks[event])
    if not hooks[event]:
        del hooks[event]
if not hooks:
    data.pop("hooks", None)
json.dump(data, open(path, "w"), indent=2, ensure_ascii=False)
print(f"[3/4] removed {removed} hook entries from {path}")
PY
else
  echo "[3/4] no settings.json found, skipping"
fi

# 4. macOS LaunchAgent
if [ "$OS" = "Darwin" ]; then
  PLIST="$HOME_DIR/Library/LaunchAgents/com.claude-code-worktree.plist"
  if [ -f "$PLIST" ]; then
    launchctl unload "$PLIST" 2>/dev/null || true
    rm "$PLIST"
    echo "[4/4] removed LaunchAgent"
  else
    echo "[4/4] LaunchAgent not found, skipping"
  fi
else
  echo "[4/4] not macOS, skipping LaunchAgent removal"
  echo "      If you added a cron job, remove it manually: crontab -e"
fi

echo
echo "Done. The repo itself is untouched — delete it manually if you want:"
echo "  rm -rf $(cd "$(dirname "$0")/.." && pwd)"
