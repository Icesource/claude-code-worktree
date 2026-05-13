#!/usr/bin/env python3
"""
Diagnose why a Claude Code session may not appear in the mindmap.

Walks the pipeline stage by stage for one session id, telling you which
stage it fell off at and what to do next.

Usage:
  mindmap --diagnose                 # auto-detect most recent session
  mindmap --diagnose <session_id>    # check a specific session
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
PROJECTS_DIR = HOME / ".claude" / "projects"
REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = REPO_ROOT / "cache"
SESSIONS_DIR = CACHE_DIR / "sessions"
AGG_FILE = CACHE_DIR / "aggregate_input.json"
MINDMAP_FILE = CACHE_DIR / "mindmap.json"
OUTPUT_FILE = MINDMAP_FILE  # alias used in cooldown calc
AI_MARKER = CACHE_DIR / "last_ai_run.epoch"

USE_COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def c(code: str, text: str) -> str:
    if not USE_COLOR:
        return text
    return f"\033[{code}m{text}\033[0m"


GREEN = "32"; RED = "31"; YELLOW = "33"; DIM = "2"; BOLD = "1"; CYAN = "36"


def ok(msg: str) -> str:  return f"{c(GREEN, '✓')} {msg}"
def bad(msg: str) -> str: return f"{c(RED, '✗')} {msg}"
def warn(msg: str) -> str: return f"{c(YELLOW, '!')} {msg}"
def info(msg: str) -> str: return f"  {msg}"
def head(msg: str) -> str: return c(BOLD, msg)


def log_path() -> Path:
    if sys.platform == "darwin":
        return HOME / "Library" / "Logs" / "claude-code-worktree.log"
    state_home = Path(os.environ.get("XDG_STATE_HOME") or HOME / ".local" / "state")
    return state_home / "claude-code-worktree" / "refresh.log"


def find_most_recent_session() -> tuple[str, Path] | None:
    """Latest-mtime jsonl under ~/.claude/projects."""
    if not PROJECTS_DIR.exists():
        return None
    latest = None
    latest_mtime = 0
    for f in PROJECTS_DIR.glob("*/*.jsonl"):
        try:
            mt = f.stat().st_mtime
        except OSError:
            continue
        if mt > latest_mtime:
            latest_mtime = mt
            latest = f
    if latest is None:
        return None
    return latest.stem, latest


def find_session(session_id: str) -> Path | None:
    """Find the jsonl for a given session_id under ~/.claude/projects."""
    for f in PROJECTS_DIR.glob(f"*/{session_id}.jsonl"):
        return f
    return None


def humanize_age(mtime: float) -> str:
    s = int(datetime.now().timestamp() - mtime)
    if s < 0: return "just now"
    if s < 60: return f"{s}s ago"
    if s < 3600: return f"{s // 60}m ago"
    if s < 86400: return f"{s // 3600}h {(s % 3600) // 60}m ago"
    return f"{s // 86400}d ago"


def grep_log_tail(n: int = 30) -> list[str]:
    path = log_path()
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return lines[-n:]
    except OSError:
        return []


def main() -> int:
    args = [a for a in sys.argv[1:] if a not in ("--diagnose",)]
    target_sid = args[0] if args else None

    print(head("Claude Code Worktree — Diagnostic"))
    print(c(DIM, "─" * 60))

    # ---- 0. Hook installation -------------------------------------------
    print("\n" + head("[0] Hook installation"))
    settings = HOME / ".claude" / "settings.json"
    if not settings.exists():
        print(bad(f"{settings} not found — hook never installed"))
        print(info(f"Run: bash {REPO_ROOT}/bin/install.sh"))
        return 1
    try:
        sdata = json.loads(settings.read_text())
    except json.JSONDecodeError:
        print(bad(f"{settings} is not valid JSON"))
        return 1
    hooks = sdata.get("hooks", {})
    stop_hooks = hooks.get("Stop") or []
    ss_hooks = hooks.get("SessionStart") or []
    bg_str = "refresh-bg.sh"
    stop_has = any(bg_str in h.get("command", "") for entry in stop_hooks for h in entry.get("hooks", []))
    ss_has   = any(bg_str in h.get("command", "") for entry in ss_hooks  for h in entry.get("hooks", []))
    print(ok("Stop hook installed") if stop_has else bad("Stop hook missing"))
    print(ok("SessionStart hook installed") if ss_has else bad("SessionStart hook missing"))
    if not (stop_has and ss_has):
        print(info(f"Re-install: bash {REPO_ROOT}/bin/install.sh"))

    # ---- 1. Target session ----------------------------------------------
    print("\n" + head("[1] Target session"))
    if target_sid:
        jsonl = find_session(target_sid)
        if not jsonl:
            print(bad(f"session_id {target_sid} not found under {PROJECTS_DIR}"))
            return 1
        print(ok(f"using user-provided id: {target_sid}"))
    else:
        latest = find_most_recent_session()
        if not latest:
            print(bad(f"no jsonl files under {PROJECTS_DIR}"))
            return 1
        target_sid, jsonl = latest
        print(ok(f"auto-detected most recent: {target_sid}"))
    mt = jsonl.stat().st_mtime
    print(info(f"jsonl: {jsonl}"))
    print(info(f"size: {jsonl.stat().st_size} bytes · modified {humanize_age(mt)}"))

    # ---- 2. extract.py output -------------------------------------------
    print("\n" + head("[2] Stage 1: extract.py (cache/sessions/)"))
    summary_file = SESSIONS_DIR / f"{target_sid}.json"
    if summary_file.exists():
        try:
            summary = json.loads(summary_file.read_text())
        except json.JSONDecodeError:
            summary = {}
        print(ok(f"summary present: {summary_file.name}"))
        msg_n = summary.get("message_count", 0)
        umsg_n = summary.get("user_message_count", 0)
        last_act = summary.get("last_activity_at") or "?"
        print(info(f"messages: {msg_n} total, {umsg_n} user · last activity {last_act}"))
        prompt = summary.get("first_user_prompt") or ""
        if prompt:
            print(info(f"first prompt: {prompt[:140]}"))
        recent = summary.get("recent_user_prompts") or []
        if recent:
            print(info(f"recent prompts: {len(recent)}"))
        is_auto = summary.get("is_automation")
        if is_auto:
            print(warn("flagged as automation (classifier run, will be excluded)"))
    else:
        print(bad(f"summary missing: {summary_file}"))
        print(info("Stage 1 hasn't seen this session yet — hook may not have run after the new session."))
        print(info(f"Try: bash {REPO_ROOT}/bin/extract.py"))

    # ---- 3. aggregate output --------------------------------------------
    print("\n" + head("[3] Stage 2: aggregate.py (cache/aggregate_input.json)"))
    in_agg = False
    if AGG_FILE.exists():
        try:
            agg = json.loads(AGG_FILE.read_text())
            in_agg = any(e.get("session_id") == target_sid for e in agg)
            print(info(f"aggregate has {len(agg)} entries · last write {humanize_age(AGG_FILE.stat().st_mtime)}"))
        except json.JSONDecodeError:
            print(bad("aggregate_input.json corrupt"))
    else:
        print(bad("aggregate_input.json missing"))
    if in_agg:
        print(ok("session_id IS in the latest aggregate input"))
    else:
        print(bad("session_id is NOT in the latest aggregate input"))
        print(info("Causes: extract didn't see it yet, OR it was filtered (user_message_count<1, or is_automation)"))

    # ---- 4. mindmap.json ------------------------------------------------
    print("\n" + head("[4] Stage 3: AI classification (cache/mindmap.json)"))
    if MINDMAP_FILE.exists():
        try:
            mm = json.loads(MINDMAP_FILE.read_text())
        except json.JSONDecodeError:
            mm = {}
        gen = mm.get("generated_at", "?")
        print(info(f"mindmap.json generated_at: {gen} (file mtime {humanize_age(MINDMAP_FILE.stat().st_mtime)})"))
        found_init = None
        found_ws = None
        for ws in (mm.get("workspaces") or []):
            for init in (ws.get("initiatives") or []):
                if target_sid in (init.get("sessions") or []):
                    found_init = init
                    found_ws = ws
                    break
            if found_init: break
        if found_init:
            print(ok(f"session is in initiative {c(CYAN, found_init['name'])}"))
            print(info(f"  workspace: {found_ws.get('name')}"))
            print(info(f"  initiative id: {found_init.get('id')}"))
            print(info(f"  status: {found_init.get('status')}"))
        else:
            print(bad("session_id is NOT in any initiative in mindmap.json"))
            print(info("Causes: AI hasn't run since this session existed, OR AI ignored it (rare)."))
    else:
        print(bad("mindmap.json missing — never ran a refresh"))

    # ---- 5. AI run history (real, not mindmap.json mtime) ---------------
    print("\n" + head("[5] Last real AI run"))
    cooldown = int(os.environ.get("CLAUDE_WORKTREE_COOLDOWN_SECS") or 300)
    if AI_MARKER.exists():
        try:
            last_epoch = int(AI_MARKER.read_text().strip() or "0")
        except (OSError, ValueError):
            last_epoch = 0
        age_s = max(0, int(datetime.now().timestamp()) - last_epoch)
        if age_s < 60:
            age_str = f"{age_s}s ago"
        elif age_s < 3600:
            age_str = f"{age_s // 60}m {age_s % 60}s ago"
        elif age_s < 86400:
            age_str = f"{age_s // 3600}h {(age_s % 3600) // 60}m ago"
        else:
            age_str = f"{age_s // 86400}d {(age_s % 86400) // 3600}h ago"
        if age_s < cooldown:
            remaining = cooldown - age_s
            print(warn(f"in cooldown: AI ran {age_str} (<{cooldown}s)"))
            print(info(f"next hook-triggered AI run allowed in {remaining}s"))
        else:
            print(ok(f"cooldown clear: AI ran {age_str} ({age_s}s >= {cooldown}s)"))
    else:
        print(warn(f"no AI run marker yet ({AI_MARKER} missing) — has refresh.sh ever finished an AI call?"))

    # ---- 6. Recent hook & refresh outcomes ------------------------------
    print("\n" + head("[6] Recent hook outcomes"))
    lp = log_path()
    print(info(f"log: {lp}"))
    tail = grep_log_tail(80)
    if not tail:
        print(warn("log empty or unreadable"))
    else:
        # Group lines by [hook] / legacy [refresh-bg invoked] markers.
        # Each group is one invocation.
        groups: list[list[str]] = []
        cur: list[str] = []
        for line in tail:
            is_hook_start = "[hook]" in line or "refresh-bg invoked" in line
            if is_hook_start:
                if cur:
                    groups.append(cur)
                cur = [line]
            elif cur is not None:
                cur.append(line)
        if cur:
            groups.append(cur)
        # Drop any leading group that doesn't start with a hook marker
        groups = [g for g in groups if g and ("[hook]" in g[0] or "refresh-bg invoked" in g[0])]
        # Summarize the last 8 invocations
        for grp in groups[-8:]:
            hook_line = grp[0]
            # Classify outcome
            text = "\n".join(grp)
            if "SKIP-COOLDOWN" in text:
                outcome = c(YELLOW, "SKIP cooldown")
            elif "input unchanged" in text:
                outcome = c(DIM, "skip hash-same")
            elif "no sessions" in text:
                outcome = c(DIM, "skip no-sessions")
            elif "claude -p failed" in text:
                outcome = c(RED, "FAIL")
            elif "DIFF vs prior" in text:
                outcome = c(GREEN, "OK ran AI")
            elif "wrote" in text and "initiatives" in text:
                outcome = c(GREEN, "OK ran AI")
            elif "another refresh is running" in text:
                outcome = c(DIM, "skip locked")
            else:
                outcome = c(DIM, "?")
            # Pull timestamp out of hook_line — handle both old/new formats
            ts = ""
            parts = hook_line.split()
            if len(parts) >= 2 and parts[0] == "[hook]":
                ts = parts[1]
            elif len(parts) >= 2 and parts[0].startswith("[") and parts[0].endswith("]"):
                ts = parts[0].strip("[]")
            print(f"  · {ts:<28}  {outcome}")
            # If AI ran, show the DIFF lines
            for ln in grp:
                if any(s in ln for s in ("DIFF vs prior", "+ NEW initiative", "- removed initiative", "~ status change", "~ task progress", "usage:")):
                    print("      " + ln.strip())

    # ---- 7. Verdict + actions -------------------------------------------
    print("\n" + head("[7] Verdict"))
    if not (stop_has and ss_has):
        print(bad("Hooks not installed — none of the pipeline will fire on Claude Code events."))
    elif not summary_file.exists():
        print(warn("Stage 1 (extract) hasn't recorded this session yet."))
        print(info(f"→ Manually run: python3 {REPO_ROOT}/bin/extract.py && python3 {REPO_ROOT}/bin/aggregate.py > /dev/null"))
        print(info(f"→ Then: mindmap --refresh"))
    elif not in_agg:
        print(warn("Session is extracted but filtered out (user_message_count<1 or is_automation)."))
    elif not (MINDMAP_FILE.exists() and any(target_sid in (i.get('sessions') or []) for ws in (json.loads(MINDMAP_FILE.read_text()).get('workspaces') or []) for i in (ws.get('initiatives') or []))):
        # Session in aggregate but not in mindmap → AI hasn't run with this session yet
        print(warn("Session is ready for AI but isn't in mindmap.json yet."))
        print(info("Cause: AI didn't run since this session was extracted (likely cooldown skipped it)."))
        print(info(f"→ Force AI now: mindmap --refresh"))
    else:
        print(ok("All stages green — this session is classified."))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
