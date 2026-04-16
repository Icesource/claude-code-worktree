#!/usr/bin/env bash
# One-step installer for claude-code-worktree.
# Sets up: slash commands, shell wrapper, Claude Code hooks, periodic
# background refresh (macOS only), and primes the cache.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOME_DIR="$HOME"
OS="$(uname)"

echo "Installing claude-code-worktree..."
echo

# --- 1. Slash commands -------------------------------------------------------
COMMANDS_DIR="$HOME_DIR/.claude/commands"
mkdir -p "$COMMANDS_DIR"
for cmd in mindmap mindmap-refresh; do
  link="$COMMANDS_DIR/$cmd.md"
  if [ -L "$link" ] || [ -f "$link" ]; then
    rm "$link"
  fi
  ln -s "$REPO_ROOT/commands/$cmd.md" "$link"
  echo "[1/5] linked slash command: /$(basename "$cmd")"
done

# --- 2. Shell wrapper --------------------------------------------------------
LOCAL_BIN="$HOME_DIR/.local/bin"
mkdir -p "$LOCAL_BIN"
BIN_LINK="$LOCAL_BIN/mindmap"
if [ -L "$BIN_LINK" ] || [ -f "$BIN_LINK" ]; then
  rm "$BIN_LINK"
fi
ln -s "$REPO_ROOT/bin/mindmap" "$BIN_LINK"
echo "[2/5] linked shell wrapper: mindmap -> $REPO_ROOT/bin/mindmap"
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

def ensure_hook(event_name: str) -> None:
    entries = hooks.setdefault(event_name, [])
    for entry in entries:
        for h in entry.get("hooks", []):
            if h.get("command") == hook_cmd:
                return
    entries.append({
        "hooks": [{"type": "command", "command": hook_cmd}]
    })

ensure_hook("Stop")
ensure_hook("SessionStart")

with open(path, "w") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
PY
echo "[3/5] installed Claude Code hooks (Stop + SessionStart)"

# --- 4. Periodic background refresh (platform-specific) ----------------------
if [ "$OS" = "Darwin" ]; then
  LAUNCHAGENTS_DIR="$HOME_DIR/Library/LaunchAgents"
  mkdir -p "$LAUNCHAGENTS_DIR"
  PLIST_DST="$LAUNCHAGENTS_DIR/com.claude-code-worktree.plist"

  sed -e "s|__REPO__|$REPO_ROOT|g" -e "s|__HOME__|$HOME_DIR|g" \
    "$REPO_ROOT/launchd/com.claude-code-worktree.plist" > "$PLIST_DST"

  launchctl unload "$PLIST_DST" 2>/dev/null || true
  launchctl load "$PLIST_DST"
  echo "[4/5] loaded launchd fallback timer (every 2h)"
else
  echo "[4/5] skipped launchd (not macOS)"
  echo "      Optional: set up a cron job for periodic refresh:"
  echo "        0 */2 * * * bash $REPO_ROOT/bin/refresh-bg.sh"
fi

# --- 5. Prime cache -----------------------------------------------------------
echo "[5/5] priming cache (first run, may take ~30s)..."
if bash "$REPO_ROOT/bin/refresh.sh"; then
  echo
  echo "Done! Try it now:"
else
  echo
  echo "Cache priming failed (you may not be logged in to Claude Code)."
  echo "Run 'claude /login' first, then 'bash $REPO_ROOT/bin/refresh.sh'."
  echo
  echo "Once cached, try:"
fi
echo "  mindmap              # in any terminal"
echo "  !mindmap             # inside Claude Code (zero-model, instant)"
echo "  /mindmap             # inside Claude Code (tab-completes)"
echo "  mindmap --refresh    # force refresh then show"
