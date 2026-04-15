#!/usr/bin/env bash
# Refresh the claude-mindmap cache.
# 1. Incrementally extract session summaries from ~/.claude/projects
# 2. Aggregate them and feed to `claude -p` for cross-project classification
# 3. Write the structured result to cache/mindmap.json

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CACHE_DIR="$REPO_ROOT/cache"
PROMPT_FILE="$REPO_ROOT/prompts/classify.md"
OUTPUT_FILE="$CACHE_DIR/mindmap.json"
INPUT_FILE="$CACHE_DIR/aggregate_input.json"

mkdir -p "$CACHE_DIR"

echo "[refresh] $(date -Iseconds) extracting sessions..."
python3 "$REPO_ROOT/bin/extract.py"

echo "[refresh] building aggregation input..."
python3 "$REPO_ROOT/bin/aggregate.py" > "$INPUT_FILE"

n_sessions=$(python3 -c "import json; print(len(json.load(open('$INPUT_FILE'))))")
echo "[refresh] feeding $n_sessions sessions to claude -p..."

if [ "$n_sessions" -eq 0 ]; then
  echo '{"generated_at":"'"$(date -u +%Y-%m-%dT%H:%M:%SZ)"'","projects":[]}' > "$OUTPUT_FILE"
  echo "[refresh] no sessions, wrote empty mindmap"
  exit 0
fi

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

# Run claude headless. We intentionally do NOT use --bare: that mode refuses
# to read the OAuth login from the keychain, and our whole plan is to reuse
# the user's existing Claude Code subscription auth.
# --disallowedTools keeps the model from spawning tools — we want a pure
# text-in/text-out classification.
claude -p \
  --output-format text \
  --disallowedTools "Bash Edit Write Read Glob Grep" \
  < "$FULL_PROMPT_FILE" \
  > "$CACHE_DIR/_raw_output.txt"

# Extract JSON: strip code fences if present, then validate.
python3 - "$CACHE_DIR/_raw_output.txt" "$OUTPUT_FILE" <<'PY'
import json, re, sys
raw = open(sys.argv[1]).read().strip()
# Strip ```json ... ``` fences if the model added them despite instructions.
m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw, re.DOTALL)
if m:
    raw = m.group(1)
# Fallback: find first { and last }.
if not raw.startswith("{"):
    i, j = raw.find("{"), raw.rfind("}")
    if i != -1 and j != -1:
        raw = raw[i:j+1]
data = json.loads(raw)
# Always stamp with wall-clock time; don't trust the model's guess.
from datetime import datetime, timezone
data["generated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
json.dump(data, open(sys.argv[2], "w"), indent=2, ensure_ascii=False)
print(f"[refresh] wrote {sys.argv[2]} with {len(data.get('projects', []))} projects")
PY
