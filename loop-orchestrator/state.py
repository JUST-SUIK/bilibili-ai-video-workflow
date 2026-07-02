"""
进度状态管理 —— PROGRESS.md 读写 + 断点检测。

文件格式:
  ## 选题: {title}
  ## brief: PASS | 2026-07-02T10:00:00
  ## script: FAIL | 2026-07-02T10:15:00 | critical=1,high=2,medium=0
  ## material: PASS | 2026-07-02T10:20:00
  ...

只在 orchestrator 中 import，不依赖其他内部模块。
"""

from __future__ import annotations
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

# PROGRESS.md 放在项目根目录，每次运行对应一个视频选题
PROGRESS_FILE = Path(__file__).resolve().parent.parent / "PROGRESS.md"

# 并行阶段（html+tts）会同时写 PROGRESS.md，必须加锁防止竞态
_state_lock = threading.Lock()


def init(topic: str, output_dir: str) -> None:
    """首次运行，创建 PROGRESS.md 骨架。"""
    now = _now()
    with _state_lock:
        PROGRESS_FILE.write_text(
            f"# 视频制作进度\n\n"
            f"## 选题: {topic}\n"
            f"## 输出目录: {output_dir}\n"
            f"## 开始时间: {now}\n\n"
            f"---\n\n"
            f"<!-- 各阶段状态由 orchestrator 自动写入 -->\n",
            encoding="utf-8",
        )


def save(stage: str, verdict: str, details: dict | None = None) -> None:
    """记录阶段完成状态。

    Args:
        stage: 阶段名 (script / material / narration / html / tts / assembly / publish)
        verdict: PASS 或 FAIL
        details: {"critical": 1, "high": 2, "medium": 0}，FAIL 时写入原因
    """
    detail_str = ""
    if details:
        parts = [f"{k}={v}" for k, v in details.items() if v]
        if parts:
            detail_str = " | " + ", ".join(parts)

    with _state_lock:
        line = f"## {stage}: {verdict} | {_now()}{detail_str}\n"

        content = PROGRESS_FILE.read_text(encoding="utf-8")
        # 替换已有记录或追加
        if f"## {stage}:" in content:
            content = re.sub(rf"^## {re.escape(stage)}:.*$", line.rstrip(), content, flags=re.MULTILINE)
        else:
            content = content.rstrip() + "\n" + line

        PROGRESS_FILE.write_text(content, encoding="utf-8")


def is_complete(stage: str) -> bool:
    """检查某阶段是否已 PASS。用于断点续跑跳过已完成阶段。"""
    if not PROGRESS_FILE.exists():
        return False
    content = PROGRESS_FILE.read_text(encoding="utf-8")
    return bool(re.search(rf"^## {re.escape(stage)}: PASS", content, re.MULTILINE))


def get_progress(stage: str) -> str | None:
    """读取某阶段的完整状态行，不存在返回 None。"""
    if not PROGRESS_FILE.exists():
        return None
    content = PROGRESS_FILE.read_text(encoding="utf-8")
    m = re.search(rf"^## {re.escape(stage)}: (.+)$", content, re.MULTILINE)
    return m.group(1).strip() if m else None


def get_brief() -> str:
    """读取 Production Brief（brief 阶段的 maker 输出）。"""
    brief_file = Path(__file__).resolve().parent.parent / "PRODUCTION_BRIEF.md"
    if brief_file.exists():
        return brief_file.read_text(encoding="utf-8")
    return ""


def save_brief(text: str) -> None:
    """保存 Production Brief 到独立文件。"""
    brief_file = Path(__file__).resolve().parent.parent / "PRODUCTION_BRIEF.md"
    brief_file.write_text(text, encoding="utf-8")


def get_topic() -> str:
    """读取当前选题。"""
    if not PROGRESS_FILE.exists():
        return ""
    content = PROGRESS_FILE.read_text(encoding="utf-8")
    m = re.search(r"^## 选题: (.+)$", content, re.MULTILINE)
    return m.group(1).strip() if m else ""


def get_output_dir() -> str:
    """读取输出目录。"""
    if not PROGRESS_FILE.exists():
        return ""
    content = PROGRESS_FILE.read_text(encoding="utf-8")
    m = re.search(r"^## 输出目录: (.+)$", content, re.MULTILINE)
    return m.group(1).strip() if m else ""


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
