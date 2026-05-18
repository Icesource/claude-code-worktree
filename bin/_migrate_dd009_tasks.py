#!/usr/bin/env python3
"""
DD-009 one-shot migration: clean up cross-initiative task pollution.

DD-008 v1's "carry forward all PRIOR tasks" rule let mis-assigned
tasks persist permanently. After classify.py was rewritten (DD-009
§3.5) to require current-round evidence, the next classify run will
naturally evict orphans. This script does the same locally — no AI
call — so the user can preview / apply the cleanup immediately.

For each hot initiative in cache/mindmap.json:
  1. Collect "canonical evidence" = the union of tasks[] in each
     session-of-this-init's summary frontmatter.
  2. Find PRIOR tasks whose slug is NOT in the canonical set →
     these are evictees (cross-initiative pollution or stale work).
  3. Rebuild init.tasks[] from the canonical set + done-monotone
     state from PRIOR.
  4. Append the evicted tasks to cache/task_archive/<id>.json with
     eviction_reason="dd009_migration_no_evidence".

Cold initiatives are left alone (§5).

Modes:
  --dry-run    Print per-initiative diff; touch nothing.
  (default)    Apply the changes.

Usage:
  python3 bin/_migrate_dd009_tasks.py --dry-run
  python3 bin/_migrate_dd009_tasks.py

Always safe to re-run — idempotent. After the first run, hot
initiatives' tasks already reflect canonical evidence, so a
subsequent --dry-run shows zero diff.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "bin"))

from classify import (
    MINDMAP_FILE, SUMMARIES_DIR, MAX_VISIBLE_TASKS, HOT_HOURS,
    parse_frontmatter, parse_tasks_from_fm,
    slugify_task_title,
    load_task_archive, save_task_archive, atomic_write_json,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _is_hot_session(sid: str) -> tuple[bool, str | None]:
    """Return (is_hot, summary_text or None). A session is hot if its
    summary file's last_activity_at is within HOT_HOURS."""
    p = SUMMARIES_DIR / f"{sid}.md"
    if not p.exists():
        return False, None
    text = p.read_text()
    fm, _body, _raw = parse_frontmatter(text)
    la = fm.get("last_activity_at")
    if not la:
        return False, None
    try:
        la_dt = datetime.fromisoformat(la.replace("Z", "+00:00"))
    except ValueError:
        return False, None
    is_hot = la_dt >= datetime.now(timezone.utc) - timedelta(hours=HOT_HOURS)
    return is_hot, text


def _session_tasks(sid: str) -> list[dict]:
    """Return [{title, done}] from the session's summary frontmatter,
    or [] if the summary doesn't exist."""
    p = SUMMARIES_DIR / f"{sid}.md"
    if not p.exists():
        return []
    _fm, _body, raw_fm = parse_frontmatter(p.read_text())
    return parse_tasks_from_fm(raw_fm)


def _migrate_initiative(init: dict, *, dry_run: bool) -> dict:
    """Returns a dict of stats for this init."""
    init_id = init.get("id")
    sessions = init.get("sessions") or []
    prior_tasks = init.get("tasks") or []

    # Hot sessions for this initiative + their canonical tasks
    canonical_titles_by_slug: dict[str, str] = {}  # slug → latest title wording
    canonical_done: dict[str, bool] = {}
    hot_session_count = 0
    for sid in sessions:
        is_hot, _ = _is_hot_session(sid)
        if not is_hot:
            continue
        hot_session_count += 1
        for t in _session_tasks(sid):
            slug = slugify_task_title(t["title"])
            canonical_titles_by_slug[slug] = t["title"]
            if t["done"]:
                canonical_done[slug] = True

    if hot_session_count == 0:
        # Cold — DD-009 still respects §5 (no changes). Skip.
        return {"init_id": init_id, "cold": True, "kept": len(prior_tasks),
                "evicted": 0, "carried_done": 0}

    # Index PRIOR by slug
    prior_by_slug: dict[str, dict] = {}
    for pt in prior_tasks:
        if not pt.get("title"):
            continue
        slug = pt.get("id") or slugify_task_title(pt["title"])
        # Normalize stored id
        pt["id"] = slug
        prior_by_slug[slug] = pt

    # Build new task set: every canonical slug
    kept_tasks: list[dict] = []
    for slug, title in canonical_titles_by_slug.items():
        pt = prior_by_slug.get(slug)
        if pt:
            # Carry done-monotone + existing timestamps
            done = bool(pt.get("done")) or canonical_done.get(slug, False)
            kept_tasks.append({
                "id": slug,
                "title": title,                          # latest wording
                "done": done,
                **({"done_evidence": pt["done_evidence"]}
                   if pt.get("done_evidence") else {}),
            })
        else:
            # Brand-new task surfaced by this round of session summaries
            kept_tasks.append({
                "id": slug,
                "title": title,
                "done": canonical_done.get(slug, False),
            })

    # Sort: not-done first (newest by alpha — best we can do here),
    # then done; cap to MAX_VISIBLE_TASKS
    not_done = [t for t in kept_tasks if not t["done"]]
    done_tasks = [t for t in kept_tasks if t["done"]]
    visible = not_done + done_tasks[:max(0, MAX_VISIBLE_TASKS - len(not_done))]

    # Evicted: PRIOR slugs not in canonical
    evicted = [pt for slug, pt in prior_by_slug.items()
               if slug not in canonical_titles_by_slug]
    # Also overflow from cap
    overflow = kept_tasks[len(visible):]

    # Persist
    now = _now_iso()
    if not dry_run:
        # Update init.tasks + tasks_archived_count
        init["tasks"] = visible
        init["tasks_archived_count"] = len(evicted) + len(overflow)
        # Append evicted to archive
        archive_existing = {a.get("id"): a for a in load_task_archive(init_id)
                            if a.get("id")}
        for ev in evicted:
            ev["evicted_at"] = now
            ev["eviction_reason"] = "dd009_migration_no_evidence"
            archive_existing[ev["id"]] = ev
        for ov in overflow:
            ov["evicted_at"] = now
            ov["eviction_reason"] = "overflow_capped"
            archive_existing[ov["id"]] = ov
        # Visible go to archive too with no eviction marker
        for v in visible:
            archive_existing.setdefault(v["id"], dict(v))
        save_task_archive(init_id, list(archive_existing.values()))

    return {
        "init_id": init_id,
        "cold": False,
        "hot_sessions": hot_session_count,
        "kept": len(visible),
        "evicted": len(evicted) + len(overflow),
        "carried_done": sum(1 for t in visible if t["done"]),
        "evicted_titles": [t["title"] for t in evicted],
        "overflow_titles": [t["title"] for t in overflow],
    }


def main() -> int:
    dry_run = "--dry-run" in sys.argv

    if not MINDMAP_FILE.exists():
        print(f"no mindmap.json at {MINDMAP_FILE}", file=sys.stderr)
        return 1

    mm = json.loads(MINDMAP_FILE.read_text())
    total_kept = total_evicted = 0
    cold_n = hot_n = 0

    print(f"=== DD-009 task migration {'(DRY RUN)' if dry_run else ''} ===\n")
    for ws in (mm.get("workspaces") or []):
        for init in (ws.get("initiatives") or []):
            stats = _migrate_initiative(init, dry_run=dry_run)
            if stats["cold"]:
                cold_n += 1
                continue
            hot_n += 1
            total_kept += stats["kept"]
            total_evicted += stats["evicted"]
            arrow = "→"
            print(f"  {stats['init_id']:50} "
                  f"prior={stats['kept'] + stats['evicted']:>3} {arrow} "
                  f"kept={stats['kept']:>2} evicted={stats['evicted']:>2} "
                  f"(done: {stats['carried_done']})")
            if stats["evicted_titles"]:
                for t in stats["evicted_titles"][:5]:
                    print(f"      − {t[:60]}")
                if len(stats["evicted_titles"]) > 5:
                    print(f"      − ... and {len(stats['evicted_titles']) - 5} more")

    print()
    print(f"  hot initiatives processed: {hot_n}")
    print(f"  cold initiatives untouched: {cold_n}")
    print(f"  total kept:    {total_kept}")
    print(f"  total evicted: {total_evicted}")

    if not dry_run:
        atomic_write_json(MINDMAP_FILE, mm)
        print(f"\n  wrote {MINDMAP_FILE}")
    else:
        print(f"\n  (dry-run; re-run without --dry-run to apply)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
