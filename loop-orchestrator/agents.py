"""
Agent 调用封装 —— CLI 封装 + 结构化输出 + 上下文拼装。

依赖:
  - claude CLI（已在 PATH 中）
  - .agents/skills/ 目录（frame-* skills 自动加载）
  - prompts/ 目录（从 workflow JSON 提取的静态 prompt）
"""

from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path

# 项目根目录 —— 让 CLI 能发现 .agents/skills/ 和 docs/
PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"

# ── Checker 结构化输出 JSON Schema ──────────────────────────────
# claude --json-schema 强制模型输出符合此格式的 JSON
VERDICT_SCHEMA = json.dumps({
    "type": "object",
    "properties": {
        "verdict": {"enum": ["PASS", "FAIL"]},
        "critical": {"type": "integer"},
        "high": {"type": "integer"},
        "medium": {"type": "integer"},
        "low": {"type": "integer"},
        "summary": {"type": "string", "description": "一句话总结审查结论"}
    },
    "required": ["verdict", "critical", "high", "medium"]
})

# ── 模型选择 ────────────────────────────────────────────────────
# Maker: opus（深度推理，写脚本/HTML/合成）
# Light Maker: haiku（快速任务，素材收集/发布素材）
# Checker: haiku（独立验证，--json-schema 保证输出格式）
DEFAULT_MAKER = "opus"
DEFAULT_CHECKER = "haiku"
DEFAULT_TIMEOUT_MAKER = 600   # 复杂任务（HTML、合成）可能需要更久
DEFAULT_TIMEOUT_CHECKER = 300


# ═══════════════════════════════════════════════════════════════
# 上下文拼装
# ═══════════════════════════════════════════════════════════════

def build_maker_prompt(stage: str, brief: str = "", feedback: str = "") -> str:
    """拼装 Maker 的完整 prompt。

    结构: 静态 prompt 模板 + Production Brief + 上轮审查反馈

    Args:
        stage: 阶段名，对应 prompts/{stage}.md
        brief: Production Brief 全文（由 brief 阶段生成）
        feedback: 上一轮 Checker 的 FAIL 反馈（重试时用）
    """
    prompt_file = PROMPTS_DIR / f"{stage}.md"
    if not prompt_file.exists():
        raise FileNotFoundError(f"Prompt 文件不存在: {prompt_file}")

    parts = [prompt_file.read_text(encoding="utf-8")]

    if brief:
        parts.append(f"\n\n---\n## Production Brief（共享上下文）\n{brief}")

    if feedback:
        parts.append(f"\n\n---\n## ⚠️ 上一轮审查未通过，请针对性修复以下问题:\n{feedback}")

    return "".join(parts)


def build_checker_prompt(stage: str, maker_output: str, brief: str = "") -> str:
    """拼装 Checker 的完整 prompt。

    结构: 静态审查 prompt + Production Brief + Maker 输出
    """
    prompt_file = PROMPTS_DIR / f"{stage}_review.md"
    if not prompt_file.exists():
        raise FileNotFoundError(f"Prompt 文件不存在: {prompt_file}")

    parts = [prompt_file.read_text(encoding="utf-8")]

    if brief:
        parts.append(f"\n\n---\n## Production Brief\n{brief}")

    parts.append(f"\n\n---\n## 审查对象\n{maker_output}")

    return "".join(parts)


# ═══════════════════════════════════════════════════════════════
# Agent 调用
# ═══════════════════════════════════════════════════════════════

def run_maker(
    stage: str,
    brief: str = "",
    feedback: str = "",
    model: str = DEFAULT_MAKER,
    timeout: int = DEFAULT_TIMEOUT_MAKER,
) -> str:
    """运行生成 Agent。

    CLI 命令: claude --print --model={model} -p "{prompt}"

    Skills (.agents/skills/) 自动加载 —— Maker 调用 frame-* skills 时无需手动处理。
    """
    prompt = build_maker_prompt(stage, brief, feedback)
    return _call_claude(prompt, model=model, timeout=timeout, use_schema=False)


def run_checker(
    stage: str,
    maker_output: str,
    brief: str = "",
    model: str = DEFAULT_CHECKER,
    timeout: int = DEFAULT_TIMEOUT_CHECKER,
) -> dict:
    """运行审查 Agent，返回结构化 verdict dict。

    返回格式: {"verdict": "PASS", "critical": 0, "high": 1, "medium": 2, ...}
    """
    prompt = build_checker_prompt(stage, maker_output, brief)
    output = _call_claude(prompt, model=model, timeout=timeout, use_schema=True)

    try:
        return json.loads(output)
    except json.JSONDecodeError:
        # --json-schema 失败时 fallback：找最后一个含 "verdict" 的完整 JSON 对象
        # 用栈匹配 {} 深度，不靠简单正则（防 summary 含 } 的边界情况）
        import re
        verdict = _extract_verdict_json(output)
        if verdict:
            return verdict
        return {"verdict": "FAIL", "critical": 0, "high": 0, "medium": 0,
                "summary": f"Checker 输出解析失败: {output[:200]}"}


def _extract_verdict_json(text: str) -> dict | None:
    """从文本中用栈匹配提取完整 JSON 对象（含 'verdict' key 的最后一个）。

    为什么取最后一个：Checker prompt 末尾拼接了 Maker 输出全文。
    Maker 输出中可能包含示例 JSON（如攻击报告格式模板），
    取最后一个确保拿到的是 Checker 实际输出的判定结果。
    """
    import re
    matches = []
    for m in re.finditer(r'\{', text):
        start = m.start()
        depth = 0
        end = start
        for i, ch in enumerate(text[start:], start):
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        if end > start:
            candidate = text[start:end]
            if '"verdict"' in candidate:
                try:
                    matches.append(json.loads(candidate))
                except json.JSONDecodeError:
                    continue
    return matches[-1] if matches else None


# ═══════════════════════════════════════════════════════════════
# 底层 CLI 调用
# ═══════════════════════════════════════════════════════════════

def _call_claude(prompt: str, *, model: str, timeout: int, use_schema: bool) -> str:
    """封装 claude CLI 调用。"""
    cmd = [
        "claude", "--print",
        f"--model={model}",
    ]

    if use_schema:
        cmd.extend(["--json-schema", VERDICT_SCHEMA])

    cmd.extend(["-p", prompt])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(PROJECT_ROOT),
            encoding="utf-8",
        )

        if result.returncode != 0:
            stderr = result.stderr[:500] if result.stderr else "无错误输出"
            raise RuntimeError(f"claude CLI 退出码 {result.returncode}: {stderr}")

        output = result.stdout.strip()
        if not output:
            raise RuntimeError("claude CLI 返回空输出")

        return output

    except subprocess.TimeoutExpired:
        raise RuntimeError(f"claude CLI 超时 ({timeout}s)\nPrompt 前 200 字符: {prompt[:200]}")
    except FileNotFoundError:
        print("❌ 未找到 claude CLI。请确认 claude 在 PATH 中。", file=sys.stderr)
        sys.exit(1)
