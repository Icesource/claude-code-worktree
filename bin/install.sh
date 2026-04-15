#!/usr/bin/env bash
# Install claude-mindmap: symlink the slash command and load the launchd job.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOME_DIR="$HOME"

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

# 3. launchd job
LAUNCHAGENTS_DIR="$HOME_DIR/Library/LaunchAgents"
mkdir -p "$LAUNCHAGENTS_DIR"
PLIST_DST="$LAUNCHAGENTS_DIR/com.bby.claude-mindmap.plist"

sed -e "s|__REPO__|$REPO_ROOT|g" -e "s|__HOME__|$HOME_DIR|g" \
  "$REPO_ROOT/launchd/com.bby.claude-mindmap.plist" > "$PLIST_DST"
echo "[install] wrote launchd plist: $PLIST_DST"

# Reload if already loaded.
launchctl unload "$PLIST_DST" 2>/dev/null || true
launchctl load "$PLIST_DST"
echo "[install] loaded launchd job com.bby.claude-mindmap (fallback every 2h)"

echo
echo "Done. Next steps:"
echo "  - Run once now:       bash $REPO_ROOT/bin/refresh.sh"
echo "  - View (zero model):  mindmap           # in a shell"
echo "                        !mindmap          # inside Claude Code"
echo "  - View (via /cmd):    /mindmap          # inside Claude Code (tab-completes)"
echo "  - Force refresh:      mindmap --refresh / /mindmap-refresh"
echo "  - Tail logs:          tail -f ~/Library/Logs/claude-mindmap.log"
echo "  - Uninstall:          launchctl unload $PLIST_DST && rm $PLIST_DST \\"
echo "                          $COMMANDS_DIR/mindmap.md $COMMANDS_DIR/mindmap-refresh.md \\"
echo "                          $BIN_LINK"
