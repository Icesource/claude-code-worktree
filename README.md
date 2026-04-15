# claude-mindmap

A local tool that reads your Claude Code session history, uses `claude -p` to
classify sessions into projects, and renders a terminal mindmap of your recent
work — available from inside Claude Code via `/mindmap`.

```
Claude Mindmap  (generated 1m ago)
────────────────────────────────────────────────────────────
├── claude-mindmap  [● active]  4m ago  4 sessions
│   Building a tool that reads Claude Code session histories...
│   progress: Incremental session extraction done (103 sessions). Next:
│             write classify prompt and refresh.sh.
│   tasks:
│     ├─ ✓ Extract sessions from JSONL (extract.py)
│     ├─ ○ Write classify/summarize prompt
│     └─ ○ Terminal mindmap rendering
│
├── hsfops  [● active]  5h ago  22 sessions
│   ...
│
└── archived (3)
    ├─ mstest (HSF invoke testing)  (7d ago, 1s)
    ├─ v2rayN troubleshooting       (14h ago, 1s)
    └─ misc short sessions          (6h ago, 29s)
```

## How it works

1. **`bin/extract.py`** incrementally reads `~/.claude/projects/**/*.jsonl`
   (tracking `{mtime, offset}` per file in `cache/state.json`) and writes a
   structured summary per session to `cache/sessions/<id>.json`. It prefers
   Claude Code's native `away_summary` recap when present, so most sessions
   cost zero AI calls.
2. **`bin/aggregate.py`** reads those session summaries, drops noise, sorts by
   recency, and emits compact JSON for the classifier.
3. **`bin/refresh.sh`** feeds that JSON plus `prompts/classify.md` to
   `claude -p` (reusing your Claude Code subscription — no extra API key),
   producing `cache/mindmap.json`.
4. **`bin/render.py`** reads `mindmap.json` and prints a colored tree using
   only Python stdlib (no `rich`, no `pip install`).
5. **`/mindmap`** is a slash command that runs `render.py` inside Claude Code
   and shows the tree verbatim.

## Triggers

The mindmap cache is refreshed automatically by three cooperating sources:

| Source | When it fires | Role |
|--------|---------------|------|
| Claude Code `Stop` hook | After **every response turn** | Primary — keeps data fresh while you work |
| Claude Code `SessionStart` hook | When you open a Claude Code session | Primary — ensures an up-to-date mindmap when you return |
| macOS LaunchAgent (launchd) | Every 2 hours | Fallback — runs regardless of whether Claude Code is open |

All triggers go through `bin/refresh-bg.sh`, which forks to the background and
returns immediately (hooks never block) and uses an atomic `mkdir` lock to
prevent concurrent runs.

> **Note on the `Stop` hook name**: `Stop` fires at the end of each response
> turn, not at session end. In a long-running conversation it fires after every
> Claude reply, so data stays fresh naturally.

## Requirements

- macOS (launchd plist is mac-specific; everything else is portable)
- Python 3.9+
- `claude` CLI in `$PATH`, logged in (`claude /login` or the regular OAuth flow)
- An active Claude Code subscription (Pro/Max) — refresh uses your subscription
  quota, no separate `ANTHROPIC_API_KEY` needed

## Install

```bash
git clone <this-repo> ~/code/claude-mindmap
cd ~/code/claude-mindmap

# 1. Symlinks /mindmap + /mindmap-refresh slash commands, loads the
#    LaunchAgent fallback.
bash bin/install.sh

# 2. Merges Stop + SessionStart hooks into ~/.claude/settings.json.
#    Idempotent: re-running won't create duplicates.
bash bin/install-hook.sh

# 3. Prime the cache once so /mindmap has something to show immediately.
bash bin/refresh.sh
```

After step 3 you can type `/mindmap` in any Claude Code session.

## Usage

There are two ways to view the mindmap, pick whichever fits the moment:

### Zero-model path (fast, recommended)

`install.sh` symlinks a `mindmap` wrapper into `~/.local/bin`, so you can run:

```bash
mindmap              # render cached mindmap
mindmap --refresh    # force refresh first, then render
```

Inside Claude Code, use the `!` shell-passthrough prefix to get the same
zero-model behavior:

```
!mindmap
!mindmap --refresh
```

This bypasses the model entirely — output is instant, no tokens used.
The downside is `!`-commands don't tab-complete.

### Slash-command path (tab-completes, goes through model)

Claude Code does not currently support user-registered handler commands that
bypass the model (see `PLAN.md` for details). The markdown slash commands
below tab-complete on `/`, but each invocation makes a tiny model round-trip
to echo the rendered tree.

- **`/mindmap`** — show the current cached mindmap
- **`/mindmap-refresh`** — force refresh first, then show the result. Use
  right after install, or after a long break before hooks/launchd have
  caught up.

### Plain shell (for debugging)

```bash
bash ~/code/claude-mindmap/bin/refresh.sh    # regenerate cache (blocking)
python3 ~/code/claude-mindmap/bin/render.py  # just render
tail -f ~/Library/Logs/claude-mindmap.log    # watch background refreshes
```

## Project statuses

The classifier assigns each project one of four statuses:

- **`● active`** — activity within the last 3 days, work clearly ongoing
- **`◐ paused`** — 3–14 days idle, or longer but with a clear resume signal
  (open MRs, filed issues, unfinished todos)
- **`✓ done`** — explicitly finished (merged, delivered, report submitted)
- **`▪ archived`** — >14 days idle with no resume signal, or throwaway
  exploratory/debug sessions. Archived projects are collapsed to one line
  each at the bottom of the tree so they don't pollute the main view.

## Files

```
claude-mindmap/
├── bin/
│   ├── mindmap            # user-facing wrapper (symlinked to ~/.local/bin)
│   ├── extract.py         # incremental JSONL parser
│   ├── aggregate.py       # build compact classifier input
│   ├── refresh.sh         # orchestrate extract → claude -p → mindmap.json
│   ├── refresh-bg.sh      # fire-and-forget wrapper + mkdir lock
│   ├── render.py          # zero-dep ANSI tree renderer
│   ├── install.sh         # slash commands + shell wrapper + LaunchAgent
│   └── install-hook.sh    # merges hooks into ~/.claude/settings.json
├── prompts/
│   └── classify.md        # prompt given to claude -p
├── commands/
│   ├── mindmap.md         # /mindmap slash command
│   └── mindmap-refresh.md # /mindmap-refresh slash command
├── launchd/
│   └── com.bby.claude-mindmap.plist
├── cache/                 # runtime state (gitignored)
│   ├── state.json         # per-file mtime + offset cursors
│   ├── sessions/<id>.json # structured summary per session
│   ├── mindmap.json       # latest AI classification
│   └── refresh.lock.d/    # atomic lock directory
├── PLAN.md
└── README.md
```

## Troubleshooting

- **`/mindmap` says "No mindmap cache found"** — run `bash bin/refresh.sh`
  once, or use `/mindmap-refresh`.
- **Background refresh not firing** — check `~/Library/Logs/claude-mindmap.log`.
  Also `jq .hooks ~/.claude/settings.json` to confirm the hooks are installed.
  **Hooks only apply to Claude Code sessions started *after* `install-hook.sh`.**
  The session you ran the installer in will not trigger its own Stop hook
  until you reopen Claude Code. Use `mindmap --refresh` in the meantime.
- **Mindmap shows stale tasks for the session I'm currently in** — same root
  cause. The in-flight session's data is being extracted, but until you
  trigger a refresh (`mindmap --refresh`), the classifier output is frozen.
  Claude Code also only writes the native `away_summary` recap after the
  session has been idle for a bit, so very active sessions rely more on the
  extracted progress signals (`edited_files`, `task_events`, etc.).
- **"Not logged in · Please run /login"** in the log — run `claude /login`
  once interactively. Do **not** pass `--bare` to `claude -p`; that mode
  refuses to read OAuth credentials from the keychain.
- **Cache feels stale** — use `/mindmap-refresh`, or check the log to see if
  runs are being skipped by the lock (which is fine) or erroring out.

## Uninstall

```bash
launchctl unload ~/Library/LaunchAgents/com.bby.claude-mindmap.plist
rm ~/Library/LaunchAgents/com.bby.claude-mindmap.plist
rm ~/.claude/commands/mindmap.md ~/.claude/commands/mindmap-refresh.md
# Then edit ~/.claude/settings.json and remove the refresh-bg.sh entries
# from hooks.Stop and hooks.SessionStart.
```
