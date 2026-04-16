#!/usr/bin/env bash
# One-step installer for claude-code-worktree.
# Sets up: slash commands, shell wrapper, Claude Code hooks, and periodic
# background refresh (macOS only). Does NOT trigger a model call.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOME_DIR="$HOME"
OS="$(uname)"

echo "Installing claude-code-worktree..."
echo

# --- 1. Slash commands -------------------------------------------------------
# Commands use __REPO__ as a placeholder; we substitute and copy (not symlink)
# so the installed command always has the correct absolute path.
COMMANDS_DIR="$HOME_DIR/.claude/commands"
mkdir -p "$COMMANDS_DIR"
for cmd in mindmap mindmap-refresh; do
  src="$REPO_ROOT/commands/$cmd.md"
  dst="$COMMANDS_DIR/$cmd.md"
  sed "s|__REPO__|$REPO_ROOT|g" "$src" > "$dst"
  echo "[1/4] installed slash command: /$cmd"
done

# --- 2. Shell wrapper --------------------------------------------------------
LOCAL_BIN="$HOME_DIR/.local/bin"
mkdir -p "$LOCAL_BIN"
BIN_LINK="$LOCAL_BIN/mindmap"
if [ -L "$BIN_LINK" ] || [ -f "$BIN_LINK" ]; then
  rm "$BIN_LINK"
fi
ln -s "$REPO_ROOT/bin/mindmap" "$BIN_LINK"
echo "[2/4] linked shell wrapper: mindmap -> $REPO_ROOT/bin/mindmap"
if ! echo ":$PATH:" | grep -q ":$LOCAL_BIN:"; then
  echo "      WARNING: $LOCAL_BIN is not in \$PATH"
  echo "      Add to your shell rc:  export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

# --- 3. Claude Code hooks (Stop + SessionStart) ------------------------------
SETTINGS="$HOME_DIR/.claude/settings.json"
HOOK_CMD="bash $REPO_ROOT/bin/refresh-bg.sh"

if [ ! -f "$SETTINGS" ]; then
  echo "{}" > "$SETTINGS"
fi
cp "$SETTINGS" "$SETTINGS.bak.$(date +%s)"

python3 - "$SETTINGS" "$HOOK_CMD" <<'PY'
import json, sys
path, hook_cmd = sys.argv[1], sys.argv[2]
with open(path) as f:
    data = json.load(f)

hooks = data.setdefault("hooks", {})

# Clean up any stale entries (e.g. from a previous install path or rename).
for event in list(hooks.keys()):
    hooks[event] = [
        e for e in hooks[event]
        if not any(
            "refresh-bg.sh" in h.get("command", "")
            and ("claude-code-worktree" in h["command"] or "claude-mindmap" in h["command"])
            for h in e.get("hooks", [])
        )
    ]

def ensure_hook(event_name: str) -> None:
    entries = hooks.setdefault(event_name, [])
    entries.append({
        "hooks": [{"type": "command", "command": hook_cmd}]
    })

ensure_hook("Stop")
ensure_hook("SessionStart")

with open(path, "w") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
PY
echo "[3/4] installed Claude Code hooks (Stop + SessionStart)"

# --- 4. Periodic background refresh (platform-specific) ----------------------
if [ "$OS" = "Darwin" ]; then
  LAUNCHAGENTS_DIR="$HOME_DIR/Library/LaunchAgents"
  mkdir -p "$LAUNCHAGENTS_DIR"
  PLIST_DST="$LAUNCHAGENTS_DIR/com.claude-code-worktree.plist"

  sed -e "s|__REPO__|$REPO_ROOT|g" -e "s|__HOME__|$HOME_DIR|g" \
    "$REPO_ROOT/launchd/com.claude-code-worktree.plist" > "$PLIST_DST"

  launchctl unload "$PLIST_DST" 2>/dev/null || true
  launchctl load "$PLIST_DST"
  echo "[4/4] loaded launchd fallback timer (every 2h)"
else
  echo "[4/4] skipped launchd (not macOS)"
  echo "      Optional: set up a cron job for periodic refresh:"
  echo "        0 */2 * * * bash $REPO_ROOT/bin/refresh-bg.sh"
fi

echo
echo "Done! To generate your first worktree:"
echo
echo "  mindmap --refresh    # in any terminal"
echo "  !mindmap --refresh   # inside Claude Code (zero-model)"
echo "  /mindmap-refresh     # inside Claude Code (tab-completes)"
echo
echo "After that, the tree refreshes automatically in the background."
echo "View it anytime with: mindmap"
