#!/usr/bin/env bash
# Install claude-code-worktree: symlink slash commands, shell wrapper, and
# optionally load the macOS LaunchAgent for periodic background refreshes.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOME_DIR="$HOME"
OS="$(uname)"

# 1. Slash commands
COMMANDS_DIR="$HOME_DIR/.claude/commands"
mkdir -p "$COMMANDS_DIR"
for cmd in mindmap mindmap-refresh; do
  link="$COMMANDS_DIR/$cmd.md"
  if [ -L "$link" ] || [ -f "$link" ]; then
    rm "$link"
  fi
  ln -s "$REPO_ROOT/commands/$cmd.md" "$link"
  echo "[install] linked slash command: $link -> $REPO_ROOT/commands/$cmd.md"
done

# 2. Shell wrapper (for `mindmap` / `!mindmap` — zero-model path)
LOCAL_BIN="$HOME_DIR/.local/bin"
mkdir -p "$LOCAL_BIN"
BIN_LINK="$LOCAL_BIN/mindmap"
if [ -L "$BIN_LINK" ] || [ -f "$BIN_LINK" ]; then
  rm "$BIN_LINK"
fi
ln -s "$REPO_ROOT/bin/mindmap" "$BIN_LINK"
echo "[install] linked shell wrapper: $BIN_LINK -> $REPO_ROOT/bin/mindmap"
if ! echo ":$PATH:" | grep -q ":$LOCAL_BIN:"; then
  echo "[install] WARNING: $LOCAL_BIN is not in \$PATH; add it to your shell rc to use 'mindmap' / '!mindmap'"
fi

# 3. Periodic background refresh (platform-specific)
if [ "$OS" = "Darwin" ]; then
  LAUNCHAGENTS_DIR="$HOME_DIR/Library/LaunchAgents"
  mkdir -p "$LAUNCHAGENTS_DIR"
  PLIST_DST="$LAUNCHAGENTS_DIR/com.claude-code-worktree.plist"

  sed -e "s|__REPO__|$REPO_ROOT|g" -e "s|__HOME__|$HOME_DIR|g" \
    "$REPO_ROOT/launchd/com.claude-code-worktree.plist" > "$PLIST_DST"
  echo "[install] wrote launchd plist: $PLIST_DST"

  launchctl unload "$PLIST_DST" 2>/dev/null || true
  launchctl load "$PLIST_DST"
  echo "[install] loaded launchd job (fallback every 2h)"
else
  echo "[install] NOTE: Periodic refresh via launchd is macOS-only."
  echo "         On Linux, you can set up a cron job or systemd timer:"
  echo "           crontab -e"
  echo "           # Add: 0 */2 * * * bash $REPO_ROOT/bin/refresh-bg.sh"
  echo "         Or rely on Claude Code hooks (install-hook.sh) for auto-refresh."
fi

echo
echo "Done. Next steps:"
echo "  - Install hooks:      bash $REPO_ROOT/bin/install-hook.sh"
echo "  - Prime cache:        bash $REPO_ROOT/bin/refresh.sh"
echo "  - View (zero model):  mindmap           # in a shell"
echo "                        !mindmap          # inside Claude Code"
echo "  - View (via /cmd):    /mindmap          # inside Claude Code (tab-completes)"
echo "  - Force refresh:      mindmap --refresh / /mindmap-refresh"
