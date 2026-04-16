---
description: Force refresh the mindmap cache then show it
allowed-tools: Bash(bash:*), Bash(python3:*)
---

Output the text below verbatim inside a fenced code block (```text ... ```). Write nothing else — no greeting, no summary, no explanation, just the code block.

!`bash ~/code/claude-code-worktree/bin/refresh.sh >/dev/null 2>&1 && python3 ~/code/claude-code-worktree/bin/render.py`
