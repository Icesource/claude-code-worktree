You are analyzing a developer's Claude Code session history to produce a
mindmap of their recent work.

You will be given a JSON array of session summaries. Each entry has:
- `session_id`: unique session identifier
- `cwd`: working directory of the session
- `started_at` / `last_activity_at`: timestamps
- `message_count`: total messages exchanged
- `first_user_prompt`: the opening request (may be truncated)
- `recap`: Claude Code's native session recap if available (authoritative)
- `tools_used`: tool names invoked during the session

Your job:

1. Group sessions into **projects**. A project usually corresponds to a `cwd`,
   but merge cwds that clearly belong to the same logical effort (e.g. a
   frontend and backend repo working toward one feature). Split a single cwd
   into multiple projects if the sessions cover distinct goals.

2. For each project produce:
   - `name`: short human-readable name (prefer the repo/folder name)
   - `cwd`: primary working directory (or a list if merged)
   - `status`: one of `active`, `paused`, `done` — infer from recency and recap
   - `summary`: 1-2 sentences describing what the project is about
   - `progress`: 1-2 sentences on the latest state / where things stand
   - `tasks`: up to 6 concrete items with `{title, done}`. Prefer items
     explicitly mentioned as done/todo in recaps; otherwise infer from prompts.
   - `sessions`: list of contributing session_ids
   - `last_activity_at`: most recent timestamp among its sessions

3. Sort projects by `last_activity_at` descending.

4. Output **strict JSON only** matching this shape, no prose, no code fences:

```
{
  "generated_at": "<ISO-8601 UTC>",
  "projects": [
    {
      "name": "...",
      "cwd": "...",
      "status": "active|paused|done",
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
