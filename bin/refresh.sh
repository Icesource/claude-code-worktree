#!/usr/bin/env bash
# Refresh the claude-code-worktree cache.
# 1. Incrementally extract session summaries from ~/.claude/projects
# 2. Aggregate them; if content hash matches last run, skip the AI call
# 3. Otherwise feed to `claude -p` for cross-project classification
# 4. Write the structured result to cache/mindmap.json
#
# Concurrency: a single mkdir-based lock guards the whole pipeline.
# Every caller (hook, launchd, /mindmap-refresh, manual) funnels through it.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CACHE_DIR="$REPO_ROOT/cache"
PROMPT_FILE="$REPO_ROOT/prompts/classify.md"
OUTPUT_FILE="$CACHE_DIR/mindmap.json"
INPUT_FILE="$CACHE_DIR/aggregate_input.json"
HASH_FILE="$CACHE_DIR/last_input.sha256"
LOCK_DIR="$CACHE_DIR/refresh.lock.d"

mkdir -p "$CACHE_DIR"

# --- Acquire global lock (applies to every refresh path) ------------------
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  # Stale lock recovery: >10 minutes old, assume crashed and reclaim.
  if [ -d "$LOCK_DIR" ]; then
    # Stale threshold must be > CLAUDE_TIMEOUT_SECS (600s) so the legit
    # slowest run finishes before any other caller reclaims the lock.
    # stat -f %m is macOS; stat -c %Y is Linux.
    lock_mtime=$(stat -f %m "$LOCK_DIR" 2>/dev/null || stat -c %Y "$LOCK_DIR" 2>/dev/null || echo 0)
    lock_age=$(( $(date +%s) - lock_mtime ))
    if [ "$lock_age" -gt 660 ]; then
      rm -rf "$LOCK_DIR"
      mkdir "$LOCK_DIR"
    else
      echo "[refresh] another refresh is running, skip"
      exit 0
    fi
  fi
fi
trap 'rm -rf "$LOCK_DIR"' EXIT

# --- Pipeline --------------------------------------------------------------
echo "[refresh] $(date -Iseconds) extracting sessions..."
python3 "$REPO_ROOT/bin/extract.py"

echo "[refresh] building aggregation input..."
python3 "$REPO_ROOT/bin/aggregate.py" > "$INPUT_FILE"

n_sessions=$(python3 -c "import json; print(len(json.load(open('$INPUT_FILE'))))")

if [ "$n_sessions" -eq 0 ]; then
  echo '{"generated_at":"'"$(date -u +%Y-%m-%dT%H:%M:%SZ)"'","projects":[]}' > "$OUTPUT_FILE"
  echo "[refresh] no sessions, wrote empty mindmap"
  exit 0
fi

# --- Skip AI when the aggregated input hasn't changed ---------------------
# extract.py is already incremental; aggregate.py is deterministic for a
# given session cache. So if the hash of aggregate_input.json matches the
# last successful run AND mindmap.json exists, nothing real has changed
# and we can just refresh the `generated_at` timestamp.
new_hash=$(shasum -a 256 "$INPUT_FILE" | awk '{print $1}')
if [ -f "$HASH_FILE" ] && [ -f "$OUTPUT_FILE" ] && [ "$(cat "$HASH_FILE")" = "$new_hash" ]; then
  python3 - "$OUTPUT_FILE" <<'PY'
import json, sys
from datetime import datetime, timezone
path = sys.argv[1]
data = json.load(open(path))
data["generated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
json.dump(data, open(path, "w"), indent=2, ensure_ascii=False)
PY
  echo "[refresh] input unchanged ($new_hash), reused cached mindmap ($n_sessions sessions)"
  exit 0
fi

input_kb=$(( $(wc -c < "$INPUT_FILE") / 1024 ))
echo "[refresh] input changed, feeding $n_sessions sessions (${input_kb}KB) to claude -p..."

# Build the full prompt: instructions + input data.
NOW_ISO=$(date -u +%Y-%m-%dT%H:%M:%SZ)
FULL_PROMPT_FILE="$CACHE_DIR/_prompt.txt"
{
  cat "$PROMPT_FILE"
  echo
  echo "CURRENT_TIME: $NOW_ISO"
  echo "(Use this as the reference point when computing session age.)"
  echo
  echo "INPUT SESSIONS:"
  cat "$INPUT_FILE"
} > "$FULL_PROMPT_FILE"

prompt_kb=$(( $(wc -c < "$FULL_PROMPT_FILE") / 1024 ))

# Run claude headless, with a timeout so a stuck run cannot block everyone.
# We use --output-format json to capture token usage metrics.
# macOS has no `timeout` binary; `perl -e 'alarm ...; exec'` is portable.
# We intentionally do NOT use --bare: that mode refuses to read the OAuth
# login from the keychain, and our whole plan is to reuse the user's
# existing Claude Code subscription auth.
# --disallowedTools keeps the model from spawning tools — we want a pure
# text-in/text-out classification.
CLAUDE_TIMEOUT_SECS="${CLAUDE_MINDMAP_TIMEOUT:-600}"
t_start=$(date +%s)
if ! perl -e 'alarm shift @ARGV; exec @ARGV' "$CLAUDE_TIMEOUT_SECS" \
    claude -p \
      --output-format json \
      --disallowedTools "Bash Edit Write Read Glob Grep" \
      < "$FULL_PROMPT_FILE" \
      > "$CACHE_DIR/_raw_output.json"; then
  rc=$?
  t_elapsed=$(( $(date +%s) - t_start ))
  echo "[refresh] claude -p failed or timed out after ${t_elapsed}s (rc=$rc), abandoning" >&2
  echo "[refresh]   prompt=${prompt_kb}KB  sessions=$n_sessions" >&2
  exit 1
fi
t_elapsed=$(( $(date +%s) - t_start ))

# Extract the text result and usage stats from JSON envelope, then parse
# the mindmap JSON from the model's text output.
python3 - "$CACHE_DIR/_raw_output.json" "$OUTPUT_FILE" "$prompt_kb" "$t_elapsed" <<'PY'
import json, re, sys

envelope = json.load(open(sys.argv[1]))
prompt_kb = sys.argv[3]
elapsed = sys.argv[4]

# --- Log usage stats --------------------------------------------------------
usage = envelope.get("usage", {})
in_tok = usage.get("input_tokens", 0) + usage.get("cache_read_input_tokens", 0)
cache_create = usage.get("cache_creation_input_tokens", 0)
out_tok = usage.get("output_tokens", 0)
cost = envelope.get("total_cost_usd", 0)
print(f"[refresh] usage: in={in_tok} (+{cache_create} cache-create) out={out_tok} "
      f"cost=${cost:.4f} prompt={prompt_kb}KB elapsed={elapsed}s")

# --- Extract mindmap JSON from model text -----------------------------------
raw = (envelope.get("result") or "").strip()
m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw, re.DOTALL)
if m:
    raw = m.group(1)
if not raw.startswith("{"):
    i, j = raw.find("{"), raw.rfind("}")
    if i != -1 and j != -1:
        raw = raw[i:j+1]
data = json.loads(raw)
from datetime import datetime, timezone
data["generated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
json.dump(data, open(sys.argv[2], "w"), indent=2, ensure_ascii=False)
print(f"[refresh] wrote {sys.argv[2]} with {len(data.get('projects', []))} projects")
PY

# Record the hash only after a fully successful claude -p pass.
echo "$new_hash" > "$HASH_FILE"
