#!/usr/bin/env python3
"""
Incrementally extract session summaries from Claude Code jsonl logs.

Reads ~/.claude/projects/**/*.jsonl, tracks per-file (mtime, byte_offset) in
cache/state.json, and writes per-session summaries to cache/sessions/<id>.json.

Prefers the native `away_summary` recap when present; otherwise falls back to
the first user prompt as a lightweight stand-in (Level-1 AI summarization can
fill this later).
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

HOME = Path.home()
PROJECTS_DIR = HOME / ".claude" / "projects"
REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = REPO_ROOT / "cache"
SESSIONS_DIR = CACHE_DIR / "sessions"
STATE_FILE = CACHE_DIR / "state.json"


@dataclass
class SessionSummary:
    session_id: str
    cwd: str | None = None
    source_file: str = ""
    started_at: str | None = None
    last_activity_at: str | None = None
    message_count: int = 0
    user_message_count: int = 0
    first_user_prompt: str | None = None
    recap: str | None = None  # away_summary content (latest wins)
    tools_used: list[str] = field(default_factory=list)


def load_state() -> dict[str, dict[str, Any]]:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def save_state(state: dict[str, dict[str, Any]]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False))


def load_session(session_id: str) -> SessionSummary | None:
    path = SESSIONS_DIR / f"{session_id}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    return SessionSummary(**data)


def save_session(summary: SessionSummary) -> None:
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    path = SESSIONS_DIR / f"{summary.session_id}.json"
    path.write_text(json.dumps(asdict(summary), indent=2, ensure_ascii=False))


def extract_text_from_message(msg: Any) -> str:
    """Claude Code message content can be a string or a list of blocks."""
    if isinstance(msg, str):
        return msg
    if isinstance(msg, dict):
        content = msg.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(block.get("text", ""))
            return "\n".join(parts)
    return ""


def apply_record(summary: SessionSummary, rec: dict[str, Any]) -> None:
    t = rec.get("type")
    ts = rec.get("timestamp")
    if ts:
        if summary.started_at is None or ts < summary.started_at:
            summary.started_at = ts
        if summary.last_activity_at is None or ts > summary.last_activity_at:
            summary.last_activity_at = ts
    if summary.cwd is None:
        summary.cwd = rec.get("cwd")

    if t == "user":
        summary.message_count += 1
        msg = rec.get("message") or {}
        # Skip tool_result pseudo-user messages: real prompts have string or text blocks
        text = extract_text_from_message(msg).strip()
        if text and not rec.get("toolUseResult"):
            summary.user_message_count += 1
            if summary.first_user_prompt is None:
                summary.first_user_prompt = text[:500]
    elif t == "assistant":
        summary.message_count += 1
        msg = rec.get("message") or {}
        content = msg.get("content") if isinstance(msg, dict) else None
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    name = block.get("name")
                    if name and name not in summary.tools_used:
                        summary.tools_used.append(name)
    elif t == "system":
        if rec.get("subtype") == "away_summary":
            content = rec.get("content")
            if isinstance(content, str) and content.strip():
                summary.recap = content.strip()


def process_file(path: Path, state: dict[str, dict[str, Any]]) -> int:
    """Read a single jsonl, return number of records applied."""
    key = str(path)
    stat = path.stat()
    prev = state.get(key, {})
    prev_mtime = prev.get("mtime", 0)
    prev_offset = prev.get("offset", 0)

    if stat.st_mtime == prev_mtime and stat.st_size == prev.get("size", 0):
        return 0

    # If file shrank (rotation/rewrite), restart from 0.
    start = prev_offset if stat.st_size >= prev_offset else 0

    session_id = path.stem
    summary = load_session(session_id) or SessionSummary(
        session_id=session_id, source_file=key
    )

    applied = 0
    with path.open("rb") as f:
        f.seek(start)
        for raw in f:
            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            apply_record(summary, rec)
            applied += 1

    if applied:
        save_session(summary)

    state[key] = {
        "mtime": stat.st_mtime,
        "size": stat.st_size,
        "offset": stat.st_size,
    }
    return applied


def main() -> int:
    if not PROJECTS_DIR.exists():
        print(f"projects dir not found: {PROJECTS_DIR}", file=sys.stderr)
        return 1

    state = load_state()
    files = sorted(PROJECTS_DIR.glob("*/*.jsonl"))
    total_applied = 0
    touched_files = 0

    for f in files:
        applied = process_file(f, state)
        if applied:
            touched_files += 1
            total_applied += applied

    save_state(state)
    print(
        f"scanned {len(files)} files, updated {touched_files}, "
        f"applied {total_applied} new records"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
