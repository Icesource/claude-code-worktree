# Claude Mindmap

一个为 Claude Code 提供"会话脑图"能力的本地工具：定时读取历史会话，用 AI 自动分类工作项目与进展，最终通过 `/脑图` 命令在终端以 shell 风格树状图呈现。

## 背景与动机

Claude Code 会话记录以 jsonl 形式存在本地 (`~/.claude/projects/<encoded-cwd>/*.jsonl`)，但用户没有跨会话、跨项目的全局视角。本工具希望解决：

- 我最近在做哪些项目？各自进展到哪一步？
- 不同会话之间的任务如何归类？
- 不用主动翻历史，就能看到一张"工作全景图"。

## 核心需求

1. **数据源**：读取 `~/.claude/projects/**/*.jsonl`，解析消息、工具调用、时间戳、cwd 等
2. **AI 分类总结**：调用 `claude -p` (headless 模式) 让 Claude 自己对会话做分类与进展摘要
3. **后台定时运行**：通过 launchd 定时触发，无需用户手动调用
4. **终端渲染**：shell 风格树状图（Unicode box-drawing + ANSI 颜色）
5. **快速查看**：`/脑图` slash command 直接读取缓存结果，秒开

## 架构

```
┌─────────────────────────────────────────────────────────┐
│  launchd (每小时触发)                                    │
│    └─> bin/refresh.sh                                   │
│          ├─> 读取 ~/.claude/projects/**/*.jsonl          │
│          ├─> 压缩/抽取关键信息 (prompt, cwd, 时间)        │
│          ├─> claude -p "分类并总结这些会话..." < input    │
│          └─> 输出 cache/mindmap.json                    │
└─────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│  ~/.claude/commands/脑图.md (slash command)              │
│    └─> 调用 bin/render.py cache/mindmap.json            │
│          └─> 用 rich.tree.Tree 渲染到终端                │
└─────────────────────────────────────────────────────────┘
```

## 认证方案

使用 **方案 2：Headless Claude Code**。
刷新脚本里直接调用 `claude -p "..."`，复用当前用户登录的 Claude Code OAuth 凭据，走订阅额度，不需要额外 `ANTHROPIC_API_KEY`，也不产生独立 API 计费。

## 目录结构

```
claude-mindmap/
├── PLAN.md                 # 本文件
├── README.md               # 安装与使用说明 (后续补)
├── bin/
│   ├── refresh.sh          # launchd 入口：抽取 + 调用 claude -p + 写缓存
│   ├── extract.py          # 解析 jsonl，抽取关键字段，压缩上下文
│   └── render.py           # 读缓存 JSON，用 rich 渲染树
├── prompts/
│   └── classify.md         # 给 claude -p 的分类/总结提示词
├── cache/
│   └── mindmap.json        # AI 输出的结构化结果 (gitignore)
├── launchd/
│   └── com.bby.claude-mindmap.plist   # launchd 定时任务模板
└── commands/
    └── 脑图.md              # slash command 模板 (软链到 ~/.claude/commands/)
```

## 数据流

1. **extract.py** 遍历 jsonl，按 cwd 分组，每个会话抽取：session_id、起止时间、首条 user prompt、最后一条 assistant 消息摘要、用过的工具类型。控制在 token 预算内（长会话截断）。
2. **refresh.sh** 把 extract 结果通过 stdin 喂给 `claude -p --output-format json`，prompt 让 Claude 输出严格 JSON：
   ```json
   {
     "projects": [
       {
         "name": "claude-mindmap",
         "status": "设计阶段",
         "summary": "...",
         "sessions": ["abc123", "def456"],
         "tasks": [
           {"title": "梳理方案", "done": true},
           {"title": "写 extract.py", "done": false}
         ]
       }
     ]
   }
   ```
3. **render.py** 用 `rich.tree.Tree` 渲染：项目名（粗体蓝）→ 状态（绿/黄）→ 任务列表（✓/○）。

## Slash Command

`~/.claude/commands/脑图.md`：

```markdown
---
description: 显示工作项目脑图
---
运行 `python ~/code/claude-mindmap/bin/render.py` 并把输出原样展示给我。
```

## 定时任务 (launchd)

每小时触发一次 `bin/refresh.sh`，日志写到 `~/Library/Logs/claude-mindmap.log`。
用户可通过 `launchctl load/unload` 控制开关。

## 里程碑

- [x] M0：梳理方案（本文件）
- [ ] M1：`extract.py` 能解析 jsonl 并输出结构化摘要
- [ ] M2：`refresh.sh` 跑通 `claude -p` 并产出 cache JSON
- [ ] M3：`render.py` 终端渲染效果满意
- [ ] M4：launchd plist + slash command 安装脚本
- [ ] M5：README、错误处理、长会话截断策略

## 已知风险

- jsonl 格式随 Claude Code 版本变动：用宽松解析，字段缺失时跳过
- `claude -p` 在无 TTY 环境下的行为需验证（launchd 启动时没有终端）
- 订阅额度消耗：定时任务频率不宜过高，默认每小时，可调
- 长历史 token 超限：extract 阶段做截断 + 摘要压缩
