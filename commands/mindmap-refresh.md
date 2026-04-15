---
description: Force refresh the mindmap cache and show the result
---

Run `bash ~/code/claude-mindmap/bin/refresh.sh` and wait for it to finish. This will re-extract all sessions, call `claude -p` to classify them, and rewrite `cache/mindmap.json`.

Then run `python3 ~/code/claude-mindmap/bin/render.py` and show its output to me verbatim inside a fenced code block. Do not interpret or summarize the tree — I just want to see the rendered result.

If the refresh step prints errors, show them.
