You are analyzing a developer's Claude Code session history to produce a
mindmap of their recent work.

You will be given a JSON array of session summaries. Each entry has:
- `session_id`: unique session identifier
- `cwd`: working directory of the session
- `started_at` / `last_activity_at`: timestamps
- `message_count`: total messages exchanged
- `first_user_prompt`: the opening request (may be truncated) — describes
  *what the user set out to do*
- `recent_user_prompts`: up to 3 most recent user prompts — describes
  *where the conversation currently stands / what's being asked right now*
- `last_assistant_summary`: first paragraph of the most recent assistant
  text reply — often an explicit "here's what I did" summary
- `edited_files`: files touched by Write/Edit tool calls — concrete
  evidence of what was built or changed
- `task_events`: TaskCreate/TaskUpdate events ("created: …",
  "completed: #id", "in_progress: #id") — a live progress log when the
  user relies on the task tool
- `recap`: Claude Code's native session recap if available (authoritative)
- `tools_used`: tool names invoked during the session

**Trusting the signals (in order of authority)**:
1. `task_events` with `completed:` — highest confidence "this got done"
2. `edited_files` — if a file was written, that work happened
3. `last_assistant_summary` — usually reflects the most recent state
4. `recap` — authoritative but may lag on very active sessions
5. `recent_user_prompts` — what the user is currently focused on
6. `first_user_prompt` — only the *original* goal, often stale by now

**Crucial**: do NOT list as a `{done: false}` task something that the
`edited_files`, `last_assistant_summary`, or `task_events` fields clearly
show was completed. Prefer the most recent signal when they conflict.

Your job:

1. Group sessions into **projects**. A project usually corresponds to a `cwd`,
   but merge cwds that clearly belong to the same logical effort (e.g. a
   frontend and backend repo working toward one feature). Split a single cwd
   into multiple projects if the sessions cover distinct goals.

2. For each project produce:
   - `name`: short human-readable name (prefer the repo/folder name)
   - `cwd`: primary working directory (or a list if merged)
   - `status`: one of `active`, `paused`, `done`, `archived`. Rules:
     * `active` — last activity within the past 3 days, work clearly ongoing
     * `paused` — last activity 3–14 days ago, or longer but with a clear
       "resume later" signal (open todos, unfinished MRs, waiting on someone)
     * `done` — explicitly finished: shipped, merged, report delivered, or
       recap/prompt indicates completion
     * `archived` — last activity >14 days ago AND no clear resumption signal.
       Also use this for one-off exploratory sessions, failed experiments,
       throwaway debugging, or anything unlikely to have ongoing value.
     When in doubt between `paused` and `archived`, check whether the work
     produced durable artifacts (merged code, filed issues) — if yes,
     `paused`; if no, `archived`.
   - `summary`: 1-2 sentences describing what the project is about
   - `progress`: 1-2 sentences on the latest state / where things stand
   - `tasks`: up to 6 concrete items with `{title, done}`. Prefer items
     explicitly mentioned as done/todo in recaps; otherwise infer from prompts.
   - `sessions`: list of contributing session_ids
   - `last_activity_at`: most recent timestamp among its sessions

3. Sort projects by `last_activity_at` descending.

4. Sort `archived` projects to the end of the list, regardless of their
   timestamp. Within each status group, sort by `last_activity_at` desc.

5. Output **strict JSON only** matching this shape, no prose, no code fences:

```
{
  "generated_at": "<ISO-8601 UTC>",
  "projects": [
    {
      "name": "...",
      "cwd": "...",
      "status": "active|paused|done|archived",
      "summary": "...",
      "progress": "...",
      "tasks": [{"title": "...", "done": true|false}],
      "sessions": ["..."],
      "last_activity_at": "..."
    }
  ]
}
```

Rules:
- Prefer `recap` over `first_user_prompt` when both exist — recaps are
  authoritative.
- Be concise. Summaries should read like a status report, not a transcript.
- If the input is empty, output `{"generated_at": "...", "projects": []}`.
- Never invent sessions or tasks that aren't supported by the input.
