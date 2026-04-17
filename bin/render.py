#!/usr/bin/env python3
"""
Render cache/mindmap.json as a shell-style tree with ANSI colors.

Zero external dependencies — just stdlib. Honors NO_COLOR and non-TTY stdout
(strips colors when piped).
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MINDMAP_FILE = REPO_ROOT / "cache" / "mindmap.json"

USE_COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def c(code: str, text: str) -> str:
    if not USE_COLOR:
        return text
    return f"\033[{code}m{text}\033[0m"


BOLD = "1"
DIM = "2"
BLUE = "34"
GREEN = "32"
YELLOW = "33"
RED = "31"
CYAN = "36"
MAGENTA = "35"

STATUS_STYLE = {
    "active": ("●", GREEN),
    "paused": ("◐", YELLOW),
    "done": ("✓", DIM),
    "archived": ("▪", DIM),
}


def humanize_age(iso: str | None) -> str:
    if not iso:
        return "?"
    try:
        t = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return iso
    now = datetime.now(timezone.utc)
    delta = now - t
    s = int(delta.total_seconds())
    if s < 0:
        return "just now"
    if s < 60:
        return f"{s}s ago"
    if s < 3600:
        return f"{s // 60}m ago"
    if s < 86400:
        return f"{s // 3600}h ago"
    return f"{s // 86400}d ago"


def short_cwd(cwd: str | None) -> str:
    if not cwd:
        return ""
    home = str(Path.home())
    if cwd.startswith(home):
        return "~" + cwd[len(home):]
    return cwd


def wrap_indent(text: str, indent: str, width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    cur = indent
    for w in words:
        if len(cur) + len(w) + 1 > width and cur.strip():
            lines.append(cur)
            cur = indent + w
        else:
            cur = f"{cur}{' ' if cur != indent else ''}{w}"
    if cur.strip():
        lines.append(cur)
    return lines


def render(data: dict) -> str:
    out: list[str] = []
    projects = data.get("projects", [])
    generated = data.get("generated_at", "?")

    header = c(BOLD, "Claude Code Worktree")
    age = c(DIM, f"  (generated {humanize_age(generated)})")
    out.append(f"{header}{age}")
    out.append(c(DIM, "─" * 60))

    if not projects:
        out.append(c(DIM, "  (no projects — run bin/refresh.sh)"))
        return "\n".join(out)

    try:
        term_width = max(60, min(100, os.get_terminal_size().columns)) if sys.stdout.isatty() else 100
    except OSError:
        term_width = 100

    live = [p for p in projects if p.get("status") != "archived"]
    archived = [p for p in projects if p.get("status") == "archived"]

    for pi, proj in enumerate(live):
        last = pi == len(live) - 1 and not archived
        branch = "└── " if last else "├── "
        pipe = "    " if last else "│   "

        status = proj.get("status", "?")
        icon, color = STATUS_STYLE.get(status, ("?", MAGENTA))
        name = c(BOLD, c(BLUE, proj.get("name", "unnamed")))
        status_tag = c(color, f"[{icon} {status}]")
        age_tag = c(DIM, humanize_age(proj.get("last_activity_at")))
        sess_count = len(proj.get("sessions", []))
        sess_tag = c(DIM, f"{sess_count} session{'s' if sess_count != 1 else ''}")

        out.append(f"{branch}{name}  {status_tag}  {age_tag}  {sess_tag}")

        cwd = short_cwd(proj.get("cwd") if isinstance(proj.get("cwd"), str) else None)
        if cwd:
            out.append(f"{pipe}{c(DIM, cwd)}")

        summary = (proj.get("summary") or "").strip()
        if summary:
            for line in wrap_indent(summary, f"{pipe}", term_width):
                out.append(line)

        progress = (proj.get("progress") or "").strip()
        if progress:
            label_plain = "progress: "
            cont_indent = f"{pipe}{' ' * len(label_plain)}"
            wrapped = wrap_indent(progress, cont_indent, term_width)
            if wrapped:
                body = wrapped[0][len(cont_indent):]
                wrapped[0] = f"{pipe}{c(CYAN, label_plain)}{body}"
            out.extend(wrapped)

        tasks = proj.get("tasks") or []
        if tasks:
            out.append(f"{pipe}{c(DIM, 'tasks:')}")
            for ti, task in enumerate(tasks):
                tlast = ti == len(tasks) - 1
                tbranch = "  └─ " if tlast else "  ├─ "
                done = task.get("done")
                mark = c(GREEN, "✓") if done else c(YELLOW, "○")
                title = task.get("title", "")
                if done:
                    title = c(DIM, title)
                out.append(f"{pipe}{tbranch}{mark} {title}")

        if not last:
            out.append("│")

    if archived:
        out.append("│")
        out.append(f"└── {c(DIM, f'archived ({len(archived)})')}")
        for ai, proj in enumerate(archived):
            alast = ai == len(archived) - 1
            abranch = "    └─ " if alast else "    ├─ "
            name = proj.get("name", "unnamed")
            age = humanize_age(proj.get("last_activity_at"))
            sess_n = len(proj.get("sessions", []))
            line = f"{abranch}{name}  ({age}, {sess_n}s)"
            out.append(c(DIM, line))

    return "\n".join(out)


def main() -> int:
    if not MINDMAP_FILE.exists():
        print(
            c(YELLOW, "No mindmap cache found. Run:")
            + f"\n  bash {REPO_ROOT}/bin/refresh.sh",
            file=sys.stderr,
        )
        return 1
    data = json.loads(MINDMAP_FILE.read_text())
    print(render(data))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
