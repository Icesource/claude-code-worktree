You are summarizing a single Claude Code session. The summary you
produce will be one of ~200 inputs to a cross-session classifier, so it
must be **dense, accurate, and machine-parseable**.

Output STRICT markdown with no preamble, no postscript, no code fences
around the whole thing.

# Inputs

Three XML blocks in the prompt body:

- `<context>` — `output_lang`, `now` (current ISO timestamp).
- `<session_meta>` — JSON object with machine-observable signals:
  `session_id`, `cwd`, `started_at`, `last_activity_at`, `user_turns`,
  `edits` (recent file edits with kind+ops), `tools` (tool→count map),
  `task_events` (TaskCreate/TaskUpdate strings if present).
- `<turns>` — the last N user-and-assistant turns of this session in
  chronological order, each labeled `### user` or `### assistant`.

The `<turns>` block is your primary source for narrative. The
`<session_meta>` block is your source for **machine facts** (which
files were touched, what tools were used, how active the session is).

# Output format

Exactly one YAML frontmatter block, then seven H1 sections in this
order. Do NOT skip a section even if empty — write "(无)" (zh) or
"(none)" (en) instead.

```
---
session_id: <copy verbatim from session_meta>
cwd: <copy verbatim>
last_activity_at: <copy verbatim>
user_turns: <copy verbatim>
updated_at: <copy from context.now>
status_guess: active | paused | done | abandoned
---

# 目标
One or two sentences describing what the user is fundamentally trying
to do. Should survive even as the session evolves (early-vs-late
turns will agree on this).

# 当前状态
Where the work stands AS OF THE LAST TURN. Be concrete. "已定位根因
EagleEyeHttpHook 传错参；修复方案明确" beats "继续调试中".

# 已下的决定
Bulleted decisions made and still in effect. Each line ≤ 80 chars.
- 采用 X 方案而非 Y（理由：…）
- 先做 A 再做 B

Skip generic decisions like "用 git 提交".

# 产物
Files concretely created or substantially edited in this session.
Cite path + kind. One per line.
- /tmp/foo.md (created)
- src/Bar.java (edited)

Read-only file inspection does NOT count as a product.

# 下一步
What the user or AI explicitly said is the next concrete action. Quote
or paraphrase tightly. If the session ended mid-thought without a
declared next step, write "(无明确)" / "(none stated)".

# 待解决
Pending questions, blockers, or things actively in flight. One per
line. If nothing pending, "(无)" / "(none)".

# 任务（建议）
Up to 8 checkbox items reflecting work done and remaining for this
specific session's effort. Use `[x]` for items the session has
clearly completed (evidence: edited_files, task_events.completed,
explicit confirmation), `[ ]` for outstanding ones. Each ≤ 60 chars.
- [x] 收集 EagleEye 数据样本
- [ ] 提交 Aone ISSUE
```

# Rules

1. **Most-recent-turn wins.** When the latest user turn redirects the
   work, describe THAT direction. The first user prompt and any old
   recap text may be stale; don't perpetuate them.

2. **status_guess heuristic:**
   - `active`: latest turn shows ongoing work, fresh decisions, or
     active editing.
   - `paused`: latest turn is mid-thought with no clear next action,
     OR `last_activity_at` is ≥ 3 days before `now`.
   - `done`: user explicitly closed it — "ship it", "merged", "完成了",
     "搞定", or AI says "this fix is complete and tested".
   - `abandoned`: latest turn shows frustration or refusal — "算了",
     "this isn't working, let me try something else", followed by no
     follow-up.

3. **Output language.** All natural-language content (the body of
   each section) is in `output_lang`. Technical terms — `HSF`, `MR`,
   `IP`, `span`, `OAuth`, `prompt`, `cache`, file paths, identifiers —
   stay in English even in Chinese mode. Frontmatter values stay
   English/raw.

4. **No fluff.** "继续推进中" / "the user is using Claude Code" are
   forbidden. Every sentence must carry concrete signal that another
   session-summary wouldn't also have.

5. **Don't invent.** If something isn't grounded in the inputs, write
   "(无)" instead of fabricating progress.

6. **Tasks (proposed) is special.** Reflect ONLY this session's
   effort, not the whole initiative. A 10-minute investigation
   session might propose 2-3 tasks; a multi-hour build session might
   propose 6-8. Don't pad.

7. **Quote sparingly.** When a quote helps, keep it to one short line
   from an actual prompt or reply. Don't paste paragraphs.

8. **Edge case: small-talk session.** If the session is genuinely a
   no-op ("你好" / "继续" / nothing meaningful), all sections except
   `目标` and `当前状态` may be `(无)`, and `status_guess` should be
   `paused` or `abandoned` as appropriate.

9. **Edge case: tool-heavy automation.** If the session ran extensive
   tool work but the user gave little narrative, derive the goal from
   `tools` + `edits` signals. Don't write "(无)" just because turns
   are sparse on text.
