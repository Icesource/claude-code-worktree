# claude-code-worktree

AI 驱动的终端工作树 — 自动将 Claude Code 会话分类为项目并追踪进度。

[English](../README.md)

## 效果

读取你的 Claude Code 会话历史,用 AI 自动分类,直接在终端渲染工作全景:

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

## 安装

```bash
git clone https://github.com/Icesource/claude-code-worktree.git ~/code/claude-code-worktree
cd ~/code/claude-code-worktree
bash bin/install.sh
```

一条命令完成所有事:创建 slash 命令符号链接、安装 `mindmap` CLI、配置 Claude
Code 自动刷新 hooks、加载 macOS 定时任务(如适用)、并首次生成缓存。

### 环境要求

- Python 3.9+
- `claude` CLI 已安装且已登录
- Claude Code 有效订阅(Pro/Max)— 复用现有额度,无需单独 API Key
- macOS 或 Linux(Windows 通过 WSL)

## 使用

### 终端(即时,零模型开销)

```bash
mindmap              # 渲染缓存的树形图
mindmap --refresh    # 先刷新再渲染
```

在 Claude Code 中,用 `!` 前缀获得同样的即时输出:

```
!mindmap
!mindmap --refresh
```

### Slash 命令(支持 Tab 补全,经过模型)

```
/mindmap             # 显示缓存的树形图
/mindmap-refresh     # 强制刷新后显示
```

## 自动刷新

工作树自动保持新鲜,正常使用无需手动刷新:

- **每次 Claude Code 响应后** — `Stop` hook 触发后台刷新
- **会话启动时** — `SessionStart` hook 确保数据最新
- **每 2 小时** — macOS LaunchAgent 兜底(Linux 可配置 cron,见安装输出)

所有刷新在后台运行,不会阻塞你的工作。

## 成本与性能

| 场景 | 花费 |
|------|------|
| 会话数据未变化 | **$0**(哈希跳过,不调用 AI) |
| 典型刷新(~50 个会话) | ~$0.01–0.05 |

每次 AI 调用在日志中记录 token 用量:

```
[refresh] usage: in=18200 (+0 cache-create) out=1500 cost=$0.0234 prompt=42KB elapsed=15s
```

## 项目状态

| 状态 | 图标 | 条件 |
|------|------|------|
| active | `●` | 3 天内有活动 |
| paused | `◐` | 3-14 天空闲,或有恢复信号 |
| done | `✓` | 明确完成 |
| archived | `▪` | 超过 14 天空闲且无恢复信号 |

## 工作原理

1. **`extract.py`** — 增量读取 `~/.claude/projects/**/*.jsonl`,生成结构化摘要。
2. **`aggregate.py`** — 过滤噪声,按时间排序,输出紧凑 JSON。
3. **`refresh.sh`** — 将会话数据 + 分类提示词喂给 `claude -p`,生成 `mindmap.json`。
4. **`render.py`** — 用 Python 标准库渲染彩色 ANSI 树形图(无需 pip install)。

## 故障排除

- **"No mindmap cache found"** — 运行 `mindmap --refresh`。
- **后台刷新未触发** — 用 `jq .hooks ~/.claude/settings.json` 确认 hook 已安装。
  Hook 仅对安装后新启动的会话生效。
- **"Not logged in"** — 运行 `claude /login`。
- **数据过时** — 运行 `mindmap --refresh`,查看日志了解原因。

## 卸载

```bash
rm ~/.claude/commands/mindmap.md ~/.claude/commands/mindmap-refresh.md
rm ~/.local/bin/mindmap

# macOS
launchctl unload ~/Library/LaunchAgents/com.claude-code-worktree.plist
rm ~/Library/LaunchAgents/com.claude-code-worktree.plist

# 编辑 ~/.claude/settings.json 删除 refresh-bg.sh 相关 hook 条目
```

## 许可证

MIT
