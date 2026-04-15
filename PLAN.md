# Claude Mindmap

一个为 Claude Code 提供"会话脑图"能力的本地工具：定时读取历史会话，用 AI 自动分类工作项目与进展，最终通过 `/mindmap` 命令在终端以 shell 风格树状图呈现。

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
5. **快速查看**：`/mindmap` slash command 直接读取缓存结果，秒开

## 架构

```
┌─────────────────────────────────────────────────────────┐
│  触发源(三选一或组合,见下节"触发策略")                 │
│    · Claude Code Stop hook       (每轮响应结束)          │
│    · Claude Code SessionStart hook (打开会话时)          │
│    · launchd LaunchAgent         (每 2h 兜底)            │
│           │                                              │
│           ▼                                              │
│    bin/refresh-bg.sh  (fire-and-forget + mkdir 锁)      │
│           └─> bin/refresh.sh                             │
│                 ├─> bin/extract.py  (增量读 jsonl)       │
│                 ├─> bin/aggregate.py (构建 AI 输入)      │
│                 ├─> claude -p < prompt                   │
│                 └─> cache/mindmap.json                   │
└─────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│  ~/.claude/commands/mindmap.md (slash command)           │
│    └─> bin/render.py cache/mindmap.json                 │
│          └─> ANSI 树形渲染到终端(零依赖)                │
└─────────────────────────────────────────────────────────┘
```

## 触发策略

定时 vs 事件驱动的权衡:

| 方案 | 优点 | 缺点 |
|------|------|------|
| launchd 每小时 | 与 Claude Code 无关,稳定 | 没用的时候也跑,不够新鲜 |
| `Stop` hook | 每轮响应后立即刷新,最新鲜 | 未开 Claude Code 时完全不触发 |
| `SessionStart` hook | 打开就刷新 | 首次刷新要等 AI 跑完 |

**采用组合:Stop + SessionStart + launchd 兜底**
- `Stop` hook 是主力 —— 用户每发送一条消息、Claude 每响应一次都触发(不是会话结束!很多人对 Stop 语义有误解)。长会话天然增量更新。
- `SessionStart` hook 在打开新会话时触发,保证"打开 Claude Code 就能看到近期"。
- launchd 每 2h 作为兜底,防止长期不用后第一次打开等 AI 太久。
- 所有触发都走 `refresh-bg.sh`:fork 到后台立即返回,不阻塞 hook;用 `mkdir` 原子锁防止并发冲突,10 分钟以上的 stale lock 自动清理。

**hook 配置写入位置**:`~/.claude/settings.json` 的 `hooks.Stop` 和 `hooks.SessionStart` 数组,由 `bin/install-hook.sh` 幂等合并。

## 认证方案

使用 **方案 2：Headless Claude Code**。
刷新脚本里直接调用 `claude -p "..."`，复用当前用户登录的 Claude Code OAuth 凭据，走订阅额度，不需要额外 `ANTHROPIC_API_KEY`，也不产生独立 API 计费。

## 目录结构

```
claude-mindmap/
├── PLAN.md                    # 本文件
├── README.md                  # 安装与使用说明 (后续补)
├── bin/
│   ├── extract.py             # 增量解析 jsonl → cache/sessions/*.json
│   ├── aggregate.py           # 聚合 sessions 为 AI 输入
│   ├── refresh.sh             # 编排 extract → aggregate → claude -p
│   ├── refresh-bg.sh          # 后台 fork + mkdir 锁,供 hook 使用
│   ├── render.py              # 零依赖 ANSI 树形渲染
│   ├── install.sh             # 安装 slash command + launchd
│   └── install-hook.sh        # 幂等合并 hooks 到 settings.json
├── prompts/
│   └── classify.md            # 给 claude -p 的分类/总结提示词
├── cache/                     # 运行时数据 (gitignore)
│   ├── state.json             # jsonl 增量游标
│   ├── sessions/<id>.json     # 每个会话的结构化摘要
│   ├── mindmap.json           # AI 聚合结果
│   └── refresh.lock.d/        # mkdir 原子锁目录
├── launchd/
│   └── com.bby.claude-mindmap.plist   # LaunchAgent 模板(兜底)
└── commands/
    └── mindmap.md             # slash command 模板 (软链到 ~/.claude/commands/)
```

## 数据流

1. **extract.py** 遍历 jsonl，按 cwd 分组，每个会话抽取：session_id、起止时间、首条 user prompt、最后一条 assistant 消息摘要、用过的工具类型。控制在 token 预算内（长会话截断）。
2. **aggregate.py** 读 `cache/sessions/*.json`,过滤 `user_message_count=0` 的壳会话,按 `last_activity_at` 倒序,截前 200 个,输出紧凑 JSON 数组。
3. **refresh.sh** 拼装 prompt:`classify.md` + `CURRENT_TIME: <now>`(作为时间锚) + aggregate 输出,喂给 `claude -p`。**不使用 `--bare`** —— 该模式不读 OAuth keychain,与我们复用订阅的方案冲突。
4. 输出 JSON 结构(strict,无 markdown):
   ```json
   {
     "generated_at": "<ISO-8601 UTC,刷新脚本墙钟覆盖>",
     "projects": [
       {
         "name": "claude-mindmap",
         "cwd": "...",
         "status": "active | paused | done | archived",
         "summary": "...",
         "progress": "...",
         "tasks": [{"title": "...", "done": true}],
         "sessions": ["abc123"],
         "last_activity_at": "..."
       }
     ]
   }
   ```
   状态语义(实际规则见 `prompts/classify.md`):
   - **active** — 近 3 天有活动,工作进行中
   - **paused** — 3–14 天无活动,或更久但有明确"待恢复"信号(未合 MR、开 issue)
   - **done** — 明确完成(合并、交付、会话里有结论)
   - **archived** — >14 天无活动且无恢复信号,或一次性探索/失败实验/废弃调试
   `archived` 项目在渲染时单独分组、折叠为单行,避免污染主视图。
5. **render.py** 纯 stdlib ANSI 渲染,无 pip 依赖。非 TTY 或 `NO_COLOR` 时自动去色。

## 增量刷新策略

全量轮询成本过高,采用多级增量:

### 文件级增量
维护 `cache/state.json`,记录每个 jsonl 的 `{path, mtime, byte_offset}`:
- mtime 未变 → 整文件跳过
- mtime 变了 → 从 `byte_offset` 继续读到 EOF(jsonl 只追加)
- 新文件 → 从头读
- 读完后更新 offset

### 会话级缓存
`cache/sessions/<session_id>.json` 保存每个会话的结构化摘要。只有内容变化过的会话才重新生成摘要。

### 两级 AI 调用
- **Level 1(单会话摘要,频繁,便宜)**
  只对变化过的会话生成摘要 → 写 `sessions/<id>.json`。
  若 jsonl 中已有 Claude Code 原生 recap 字段,直接复用,零 AI 调用。
- **Level 2(跨项目聚合,低频,稍贵)**
  把所有单会话摘要聚合送给 `claude -p`,产出 `mindmap.json`。
  触发条件:有 ≥N 个会话变化,或距上次聚合超过 X 小时。

### 稳态成本
- 全量:每次 ~所有会话数 次 AI 调用
- 增量:大多数周期 0 次调用;偶尔 Level 1 处理 1-2 个活跃会话;Level 2 聚合输入是压缩摘要,token 很小

## Slash Command

`~/.claude/commands/mindmap.md`：

```markdown
---
description: Show work mindmap of recent Claude Code sessions
---
Run `python ~/code/claude-mindmap/bin/render.py` and show the output verbatim.
```

## 定时任务 (launchd,兜底)

LaunchAgent(用户级,`~/Library/LaunchAgents/com.bby.claude-mindmap.plist`),每 2 小时触发一次 `refresh-bg.sh`,日志写到 `~/Library/Logs/claude-mindmap.log`。仅作为 hook 方案的兜底 —— 主力刷新靠 Claude Code 的 `Stop` / `SessionStart` hook。

控制:`launchctl load/unload <plist>`;查看:`launchctl list | grep claude-mindmap`。

## 里程碑

- [x] M0:梳理方案(本文件)
- [x] M1:`extract.py` 增量解析 jsonl
- [x] M2:`refresh.sh` 打通 `claude -p` 分类流水线
- [x] M3:`render.py` ANSI 树形渲染
- [x] M4:launchd plist + slash command + install.sh
- [x] M5:`archived` 状态 + Claude Code hook(Stop / SessionStart) + install-hook.sh
- [x] M6:`/mindmap-refresh` 命令、`bin/mindmap` 零模型 wrapper、README
- [ ] M7:长会话 token 截断策略、Level 1 AI 回填(为无 recap 的老会话生成摘要)

## 触发命令的设计取舍

Claude Code 没有公开"注册 `/`-prefix handler 命令不走模型"的接口 —— 内置 `/usage`、`/help` 是 CLI 源码硬编码。用户扩展(markdown command / skill / subagent)本质都是 prompt 模板,必走模型;`hook` 只能事件驱动;`!` 前缀可直通 shell 但无 `/` 自动补全。

**因此采用双路径并存**:
- **零模型路径**:`bin/mindmap` 可执行 wrapper(软链到 `~/.local/bin/mindmap`),shell 里 `mindmap` 或 Claude Code 里 `!mindmap` 直接调用 `render.py`,零 token、零延迟、无补全。
- **`/`-补全路径**:`/mindmap` / `/mindmap-refresh` 保留原 markdown command,优势是 `/` 自动补全和界面一致性,代价是每次一小轮模型 round-trip(prompt 已最小化为"原样输出注入的 shell 结果")。

让用户按场景自选,不强制二选一。

## jsonl 结构探针发现

实际文件:`~/.claude/projects/<encoded-cwd>/<session-uuid>.jsonl`,每行一个 JSON 对象,追加写入。

**消息类型 (`type` 字段)**
- `user` — 用户消息 / tool_result
- `assistant` — 模型输出
- `system` — 系统事件,通过 `subtype` 区分
- `attachment` — 附件
- `file-history-snapshot` — 文件快照
- `permission-mode` — 权限模式切换

**通用字段**
`uuid` / `parentUuid` / `timestamp` / `cwd` / `sessionId`,可用于串联消息、溯源、按目录聚合。

**recap 原生落盘 ✨**
Claude Code 的会话 recap 以 `system` + `subtype: "away_summary"` 写入 jsonl:

```json
{
  "type": "system",
  "subtype": "away_summary",
  "content": "<recap 文本>",
  "timestamp": "...",
  "uuid": "..."
}
```

**这是关键发现**:Level 1 单会话摘要可以直接读这个字段,零 AI 调用。
回退策略:若某会话没有 `away_summary`(会话太短、老版本、已被关闭 recap),才走原始消息抽取 + `claude -p` 生成摘要。

## 已知风险

- jsonl 格式随 Claude Code 版本变动：用宽松解析，字段缺失时跳过
- `claude -p` 在无 TTY 环境下的行为需验证（launchd 启动时没有终端）
- 订阅额度消耗：定时任务频率不宜过高，默认每小时，可调
- 长历史 token 超限：extract 阶段做截断 + 摘要压缩
