# claude-code-worktree

A local tool that reads your Claude Code session history, uses AI to classify
sessions into projects, and renders a terminal tree of your recent work.

[中文文档](docs/README.zh-CN.md)

## Demo

```
Claude Code Worktree  (generated 2m ago)
────────────────────────────────────────────────────────────
├── my-saas-app  [● active]  4m ago  6 sessions
│   ~/code/my-saas-app
│   Building user authentication and dashboard features.
│   progress: OAuth integration done. Working on role-based
│             access control for the admin panel.
│   tasks:
│     ├─ ✓ Set up OAuth2 login flow
│     ├─ ✓ Design dashboard layout
│     ├─ ○ Implement RBAC for admin panel
│     └─ ○ Add unit tests for auth middleware
│
├── data-pipeline  [● active]  2h ago  8 sessions
│   ~/code/data-pipeline
│   ETL pipeline for processing analytics events from Kafka.
│   progress: Kafka consumer and transform stages complete.
│             Writing the BigQuery sink connector.
│   tasks:
│     ├─ ✓ Kafka consumer with offset tracking
│     ├─ ✓ JSON schema validation stage
│     ├─ ○ BigQuery sink connector
│     └─ ○ Dead-letter queue handling
│
├── blog-redesign  [◐ paused]  5d ago  3 sessions
│   ~/code/blog
│   Migrating blog from Jekyll to Astro with new theme.
│   progress: Content migration done. Paused waiting for
│             design review from the team.
│   tasks:
│     ├─ ✓ Migrate markdown content
│     ├─ ✓ Set up Astro project structure
│     └─ ○ Apply new theme and deploy
│
└── archived (2)
    ├─ dotfiles (shell config cleanup)    (10d ago, 2s)
    └─ scratch-pad (one-off experiments)  (21d ago, 5s)
```

## How it works

1. **`bin/extract.py`** — Incrementally reads `~/.claude/projects/**/*.jsonl`
   (tracking `{mtime, offset}` per file) and writes a structured summary per
   session to `cache/sessions/<id>.json`. Prefers Claude Code's native
   `away_summary` recap when present, so most sessions cost zero AI calls.
2. **`bin/aggregate.py`** — Reads session summaries, drops noise, sorts by
   recency, emits compact JSON for the classifier.
3. **`bin/refresh.sh`** — Feeds JSON + `prompts/classify.md` to `claude -p`
   (reuses your Claude Code subscription — no extra API key), producing
   `cache/mindmap.json`. Logs token usage and cost per run.
4. **`bin/render.py`** — Reads `mindmap.json` and prints a colored tree using
   only Python stdlib (no `pip install` needed).
5. **`mindmap`** — Shell wrapper for instant rendering (`!mindmap` inside
   Claude Code).

## Triggers

The cache is refreshed automatically by cooperating sources:

| Source | When it fires | Platform |
|--------|---------------|----------|
| Claude Code `Stop` hook | After every response turn | All |
| Claude Code `SessionStart` hook | When you open a session | All |
| macOS LaunchAgent (launchd) | Every 2 hours (fallback) | macOS only |

All triggers go through `bin/refresh-bg.sh`, which forks to the background
(hooks never block) and uses an atomic `mkdir` lock to prevent concurrent runs.

> **Note**: The `Stop` hook fires at the end of each response turn, not at
> session end. Data stays fresh naturally during active conversations.

Linux/WSL users can set up an equivalent cron job or systemd timer — see
[Install](#install) for details.

## Requirements

- Python 3.9+
- `claude` CLI in `$PATH`, logged in
- An active Claude Code subscription (Pro/Max) — refresh uses your subscription
  quota, no separate `ANTHROPIC_API_KEY` needed
- macOS or Linux (Windows via WSL)

## Install

```bash
git clone https://github.com/user/claude-code-worktree.git ~/code/claude-code-worktree
cd ~/code/claude-code-worktree

# 1. Symlink slash commands + shell wrapper (+ LaunchAgent on macOS)
bash bin/install.sh

# 2. Merge Stop + SessionStart hooks into ~/.claude/settings.json
#    Idempotent — re-running won't create duplicates.
bash bin/install-hook.sh

# 3. Prime the cache (first run calls claude -p, takes ~30s)
bash bin/refresh.sh
```

After step 3, type `/mindmap` in any Claude Code session.

## Usage

### Zero-model path (instant, recommended)

```bash
mindmap              # render cached tree
mindmap --refresh    # force refresh first, then render
```

Inside Claude Code, use `!` to bypass the model:

```
!mindmap
!mindmap --refresh
```

### Slash commands (tab-complete, goes through model)

- **`/mindmap`** — show the cached tree
- **`/mindmap-refresh`** — force refresh, then show

### Shell (for debugging)

```bash
bash ~/code/claude-code-worktree/bin/refresh.sh    # regenerate cache
python3 ~/code/claude-code-worktree/bin/render.py  # just render
tail -f ~/Library/Logs/claude-code-worktree.log    # watch refreshes (macOS)
```

## Cost & Performance

Each refresh that triggers `claude -p` logs token usage to the refresh log:

```
[refresh] usage: in=18200 (+0 cache-create) out=1500 cost=$0.0234 prompt=42KB elapsed=15s
```

- **Hash shortcut**: If no session data changed since the last successful run,
  the AI call is skipped entirely (zero cost).
- **Incremental extraction**: Only new bytes in jsonl files are read.
- **Typical cost**: ~$0.01–0.05 per refresh depending on session count.

## Project Statuses

| Status | Symbol | Rule |
|--------|--------|------|
| `active` | `●` green | Activity within 3 days |
| `paused` | `◐` yellow | 3–14 days idle, or has resume signals |
| `done` | `✓` dim | Explicitly finished |
| `archived` | `▪` dim | >14 days idle, no resume signal |

Archived projects collapse to one line at the bottom of the tree.

## Comparison with Similar Tools

| Feature | claude-code-worktree | [Claude Code Canvas](https://github.com/raulriera/claude-code-canvas) | [cc-lens](https://github.com/) | [Claude Code Viewer](https://github.com/d-kimuson/claude-code-viewer) |
|---------|---------------------|-------|---------|------|
| AI project classification | Yes | No | No | No |
| Progress tracking | Yes (tasks, status) | No | No | No |
| Terminal-native | Yes (zero deps) | No (browser) | No (browser) | No (browser) |
| Auto background refresh | Yes (hooks + launchd) | No | No | No |
| Token/cost analytics | No | No | Yes | No |
| Session replay | No | No | Yes | Yes |
| Zero extra cost | Yes (reuses subscription) | N/A | N/A | N/A |

## Files

```
claude-code-worktree/
├── bin/
│   ├── mindmap            # shell wrapper (symlinked to ~/.local/bin)
│   ├── extract.py         # incremental JSONL parser
│   ├── aggregate.py       # build compact classifier input
│   ├── refresh.sh         # orchestrate extract → claude -p → mindmap.json
│   ├── refresh-bg.sh      # fire-and-forget wrapper for hooks
│   ├── render.py          # zero-dep ANSI tree renderer
│   ├── install.sh         # slash commands + shell wrapper + LaunchAgent
│   └── install-hook.sh    # merge hooks into ~/.claude/settings.json
├── prompts/
│   └── classify.md        # prompt for claude -p classifier
├── commands/
│   ├── mindmap.md         # /mindmap slash command
│   └── mindmap-refresh.md # /mindmap-refresh slash command
├── launchd/
│   └── com.claude-code-worktree.plist  # macOS periodic fallback
├── docs/
│   └── README.zh-CN.md   # Chinese documentation
└── cache/                 # runtime state (gitignored)
```

## Troubleshooting

- **`/mindmap` says "No mindmap cache found"** — run `bash bin/refresh.sh`
  once, or use `/mindmap-refresh`.
- **Background refresh not firing** — check the log file.
  Also verify hooks: `jq .hooks ~/.claude/settings.json`. Hooks only apply to
  sessions started *after* `install-hook.sh` runs.
- **"Not logged in"** — run `claude /login` once. Do not pass `--bare` to
  `claude -p`.
- **Stale data** — use `mindmap --refresh`. Check the log for skipped or failed
  runs.

## Uninstall

```bash
# macOS
launchctl unload ~/Library/LaunchAgents/com.claude-code-worktree.plist
rm ~/Library/LaunchAgents/com.claude-code-worktree.plist

# All platforms
rm ~/.claude/commands/mindmap.md ~/.claude/commands/mindmap-refresh.md
rm ~/.local/bin/mindmap
# Edit ~/.claude/settings.json and remove the refresh-bg.sh hook entries
```

## License

MIT
