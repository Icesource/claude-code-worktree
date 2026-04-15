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
