# claude-code-worktree

一个本地工具,读取你的 Claude Code 会话历史,用 AI 将会话自动分类为项目,并在终端渲染工作树。

[English](../README.md)

## 效果预览

```
Claude Code Worktree  (generated 2m ago)
────────────────────────────────────────────────────────────
├── my-saas-app  [● active]  4m ago  6 sessions
│   ~/code/my-saas-app
│   构建用户认证和仪表盘功能。
│   progress: OAuth 集成已完成,正在实现管理面板的
│             基于角色的访问控制。
│   tasks:
│     ├─ ✓ 搭建 OAuth2 登录流程
│     ├─ ✓ 设计仪表盘布局
│     ├─ ○ 实现管理面板 RBAC
│     └─ ○ 添加认证中间件单元测试
│
├── data-pipeline  [● active]  2h ago  8 sessions
│   ~/code/data-pipeline
│   从 Kafka 处理分析事件的 ETL 管道。
│   progress: Kafka 消费者和转换阶段已完成,
│             正在编写 BigQuery 输出连接器。
│   tasks:
│     ├─ ✓ 带偏移追踪的 Kafka 消费者
│     ├─ ✓ JSON schema 校验阶段
│     ├─ ○ BigQuery 输出连接器
│     └─ ○ 死信队列处理
│
└── archived (2)
    ├─ dotfiles (shell 配置清理)    (10d ago, 2s)
    └─ scratch-pad (临时实验)       (21d ago, 5s)
```

## 工作原理

1. **`bin/extract.py`** — 增量读取 `~/.claude/projects/**/*.jsonl`,按文件追踪
   `{mtime, offset}`,为每个会话生成结构化摘要。优先使用 Claude Code 的原生
   `away_summary`,大多数会话零 AI 开销。
2. **`bin/aggregate.py`** — 读取会话摘要,过滤噪声,按时间排序,输出紧凑 JSON。
3. **`bin/refresh.sh`** — 将 JSON + 分类提示词喂给 `claude -p`(复用你的 Claude
   Code 订阅认证,无需额外 API Key),生成 `cache/mindmap.json`。每次运行记录
   token 用量和花费。
4. **`bin/render.py`** — 读取 `mindmap.json`,用 Python 标准库渲染彩色树形图
   (无需 `pip install`)。
5. **`mindmap`** — Shell 封装,即时渲染(在 Claude Code 中用 `!mindmap`)。

## 自动触发

| 触发源 | 触发时机 | 平台 |
|--------|---------|------|
| Claude Code `Stop` Hook | 每次响应结束后 | 全平台 |
| Claude Code `SessionStart` Hook | 打开会话时 | 全平台 |
| macOS LaunchAgent (launchd) | 每 2 小时(兜底) | 仅 macOS |

所有触发器通过 `bin/refresh-bg.sh` 后台运行,使用 `mkdir` 原子锁防止并发。

> **说明**: `Stop` hook 在每次响应结束时触发,不是会话结束。活跃对话期间数据
> 自然保持新鲜。

Linux/WSL 用户可设置等效的 cron 定时任务,详见安装步骤。

## 环境要求

- Python 3.9+
- `claude` CLI 已安装且已登录
- Claude Code 有效订阅(Pro/Max)— 刷新使用你的订阅额度,无需单独的
  `ANTHROPIC_API_KEY`
- macOS 或 Linux(Windows 通过 WSL)

## 安装

```bash
git clone https://github.com/user/claude-code-worktree.git ~/code/claude-code-worktree
cd ~/code/claude-code-worktree

# 1. 创建符号链接(slash 命令 + shell 封装 + macOS 定时任务)
bash bin/install.sh

# 2. 将 Stop + SessionStart hook 合并到 ~/.claude/settings.json
#    幂等操作,重复运行不会创建重复项。
bash bin/install-hook.sh

# 3. 首次生成缓存(第一次运行会调用 claude -p,约 30 秒)
bash bin/refresh.sh
```

安装完成后,在任意 Claude Code 会话中输入 `/mindmap`。

## 使用方式

### 零模型路径(即时,推荐)

```bash
mindmap              # 渲染缓存的树形图
mindmap --refresh    # 先刷新再渲染
```

在 Claude Code 中,用 `!` 前缀绕过模型:

```
!mindmap
!mindmap --refresh
```

### Slash 命令(支持 Tab 补全,经过模型)

- **`/mindmap`** — 显示缓存的树形图
- **`/mindmap-refresh`** — 强制刷新后显示

## 成本与性能

每次触发 `claude -p` 的刷新会在日志中记录 token 用量:

```
[refresh] usage: in=18200 (+0 cache-create) out=1500 cost=$0.0234 prompt=42KB elapsed=15s
```

- **哈希跳过**: 如果会话数据未变化,完全跳过 AI 调用(零成本)。
- **增量提取**: 只读取 jsonl 文件中的新增字节。
- **典型花费**: 每次刷新约 $0.01–0.05,取决于会话数量。

## 项目状态

| 状态 | 符号 | 规则 |
|------|------|------|
| `active` | `●` 绿色 | 3 天内有活动 |
| `paused` | `◐` 黄色 | 3-14 天空闲,或有恢复信号 |
| `done` | `✓` 灰色 | 明确完成 |
| `archived` | `▪` 灰色 | 超过 14 天空闲且无恢复信号 |

## 故障排除

- **`/mindmap` 提示"No mindmap cache found"** — 运行 `bash bin/refresh.sh`,
  或使用 `/mindmap-refresh`。
- **后台刷新未触发** — 查看日志文件。确认 hook 已安装:
  `jq .hooks ~/.claude/settings.json`。Hook 仅对安装后新启动的会话生效。
- **"Not logged in"** — 运行 `claude /login`。
- **数据过时** — 使用 `mindmap --refresh`,查看日志了解跳过或失败的原因。

## 卸载

```bash
# macOS
launchctl unload ~/Library/LaunchAgents/com.claude-code-worktree.plist
rm ~/Library/LaunchAgents/com.claude-code-worktree.plist

# 全平台
rm ~/.claude/commands/mindmap.md ~/.claude/commands/mindmap-refresh.md
rm ~/.local/bin/mindmap
# 编辑 ~/.claude/settings.json 删除 refresh-bg.sh 相关 hook 条目
```
