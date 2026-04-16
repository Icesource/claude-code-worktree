#!/usr/bin/env python3
"""
Build the aggregation input for `claude -p`.

Reads cache/sessions/*.json, filters out trivial sessions, sorts by recency,
and writes a compact JSON array to stdout. Keeps only fields the classifier
needs so the prompt stays small.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SESSIONS_DIR = REPO_ROOT / "cache" / "sessions"

MIN_USER_MESSAGES = 1
MAX_SESSIONS = 200  # hard cap to keep prompt bounded


def main() -> int:
    if not SESSIONS_DIR.exists():
        print("[]")
        return 0

    entries = []
    for p in SESSIONS_DIR.glob("*.json"):
        try:
            d = json.loads(p.read_text())
        except json.JSONDecodeError:
            continue
        if d.get("user_message_count", 0) < MIN_USER_MESSAGES:
            continue
        if d.get("is_automation"):
            # Self-referential classify runs produced by refresh.sh — skip.
            continue
        entries.append(
            {
                "session_id": d.get("session_id"),
                "cwd": d.get("cwd"),
                "started_at": d.get("started_at"),
                "last_activity_at": d.get("last_activity_at"),
                "message_count": d.get("message_count", 0),
                "first_user_prompt": (d.get("first_user_prompt") or "")[:300],
                "recent_user_prompts": d.get("recent_user_prompts", [])[-3:],
                "last_assistant_summary": d.get("last_assistant_summary"),
                "edited_files": d.get("edited_files", [])[-15:],
                "task_events": d.get("task_events", [])[-15:],
                "recap": d.get("recap"),
                "tools_used": d.get("tools_used", [])[:10],
            }
        )

    entries.sort(key=lambda e: e.get("last_activity_at") or "", reverse=True)
    entries = entries[:MAX_SESSIONS]
    json.dump(entries, sys.stdout, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
