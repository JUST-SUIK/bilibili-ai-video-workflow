# 视频制作自主编排器

> 定义选题，编排器自动跑完 8 个阶段的制作流水线。
> Maker（生成）+ Checker（红队审查）分离，PASS 自动前进，FAIL 重试，耗尽升级。

## 快速开始

```bash
# 确保 claude CLI 在 PATH 中
claude --version

# 启动新视频制作
cd loop-orchestrator/
python orchestrator.py "大语言模型的工作原理"

# 断点续跑（上次中断后继续）
python orchestrator.py --resume

# 查看阶段依赖关系
python orchestrator.py --dry-run
```

## 架构

```
选题 "XXX"
  │
  ▼
┌──────────────────────────────────────────────┐
│                 Orchestrator                   │
│                                                │
│  brief → script → material → narration         │
│                                │                │
│                    ┌───────────┴───────────┐   │
│                    ▼                       ▼   │
│                  html                    tts    │  ← ThreadPoolExecutor 并行
│                    │                       │   │
│                    └───────────┬───────────┘   │
│                                ▼                │
│                            assembly             │
│                                │                │
│                                ▼                │
│                             publish             │
│                                                │
│  每阶段: Maker(Opus) → Checker(Haiku)          │
│  PASS → 自动继续                                │
│  FAIL → 重试(最多3次) → 耗尽 → 人工升级         │
└──────────────────────────────────────────────┘
  │
  ▼
PROGRESS.md      ← 文件系统状态记忆
PRODUCTION_BRIEF.md ← 共享上下文
```

## 文件结构

```
loop-orchestrator/
├── orchestrator.py    # 主编排逻辑：阶段定义 + 依赖解析 + 并行 + 主循环
├── agents.py          # Agent 调用封装：CLI 封装 + 结构化输出 + 上下文拼装
├── state.py           # 进度状态管理：PROGRESS.md 读写 + 断点检测
├── prompts/           # 从 bilibili-video-production.json 提取的 prompt
│   ├── brief.md
│   ├── script.md / script_review.md
│   ├── material.md / material_review.md
│   ├── narration.md / narration_review.md
│   ├── html.md / html_review.md
│   ├── tts.md / tts_review.md
│   ├── assembly.md / assembly_review.md
│   └── publish.md / publish_review.md
└── README.md
```

## 核心设计决策

### Maker-Checker 分离

| | Maker | Checker |
|---|---|---|
| 模型 | Opus（深度推理） | Haiku（独立验证） |
| 权限 | 完整（读写+执行） | 只读（无 Write/Edit/Bash） |
| 输出 | 自由文本 | `--json-schema` 强制 JSON |
| 职责 | 生成产物 | 验证产物 |

Checker 输出格式：
```json
{"verdict": "PASS", "critical": 0, "high": 1, "medium": 2, "summary": "..."}
```

### 并行策略

HTML 和 TTS 写不同目录（`frames/` vs `audio/`），零冲突。用 `ThreadPoolExecutor` 并发，不需要 git worktree。

### 断点续跑

`PROGRESS.md` 记录每个阶段的 PASS/FAIL 状态和时间戳。`--resume` 启动时跳过已完成阶段。上下文溢出后重启，从上次中断处继续。

### 已知限制（诚实标注）

| 限制 | 说明 |
|------|------|
| AND-join 无引擎级同步 | HTML/TTS 依赖 `assembly` 阶段隐式等待——当 `run_stage("assembly")` 检查 `deps_met()` 时自然同步 |
| 重试计数器为代码级 | `max_retries` 在 Python 的 for 循环中实现，不在 JSON 中 |
| 上下文传递依赖对话历史 | Production Brief 通过 `--append-system-prompt` 层级拼接 |
| 无独立 Checker 权限隔离 | CLI 调用无法在进程级限制工具，依赖 prompt 约束 |

## Token 预算

单视频硬上限：**200 万 token**。每次 Agent 调用后累计估算值，超限抛异常停止。

## 与工作流 JSON 的关系

`prompts/` 目录下的文件从 `workflows/bilibili-video-production.json` 提取。修改 prompt 后需要重新提取：

```bash
cd ..  # 回到项目根目录
python3 -c "
import json
with open('workflows/bilibili-video-production.json','r',encoding='utf-8') as f:
    wf = json.load(f)
# ... 提取逻辑见 agents.py 的 prompt 文件列表
"
```
