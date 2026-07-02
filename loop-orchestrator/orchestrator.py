"""
Loop Engineering 视频制作编排器。

用法:
  python orchestrator.py "视频选题标题"

示例:
  python orchestrator.py "大语言模型的工作原理"
  python orchestrator.py --resume               # 断点续跑

架构:
  Maker(Opus) → Checker(Haiku, --json-schema) → PASS 继续 / FAIL 重试 / 3次→升级
  HTML 和 TTS 并行执行（ThreadPoolExecutor）
  进度持久化到 PROGRESS.md，支持断点续跑
"""

from __future__ import annotations
import argparse
import os
import signal
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# 确保能从 loop-orchestrator/ 目录运行
sys.path.insert(0, str(Path(__file__).resolve().parent))

from agents import run_maker, run_checker
from state import init as state_init, save as state_save, is_complete, get_progress
from state import get_brief, save_brief, get_topic, get_output_dir

# ═══════════════════════════════════════════════════════════════
# 阶段定义
# ═══════════════════════════════════════════════════════════════
#
# name:          阶段名（对应 prompts/{name}.md）
# maker_model:   生成 Agent 使用的模型
# checker_model: 审查 Agent 使用的模型（None = 跳过审查）
# depends:       前置依赖阶段列表
# parallel_group: 同组阶段并行执行（html + tts）
# max_retries:   最大重试次数（不含首次尝试；总执行次数 = max_retries + 1）
#
STAGES: list[dict] = [
    {
        "name": "brief",
        "maker_model": "opus",
        "checker_model": None,        # Brief 不需要红队审查
        "depends": [],
        "parallel_group": None,
        "max_retries": 0,
    },
    {
        "name": "script",
        "maker_model": "opus",
        "checker_model": "haiku",
        "depends": ["brief"],
        "parallel_group": None,
        "max_retries": 3,
    },
    {
        "name": "material",
        "maker_model": "haiku",
        "checker_model": "haiku",
        "depends": ["script"],
        "parallel_group": None,
        "max_retries": 3,
    },
    {
        "name": "narration",
        "maker_model": "opus",
        "checker_model": "haiku",
        "depends": ["material"],
        "parallel_group": None,
        "max_retries": 3,
    },
    {
        "name": "html",
        "maker_model": "opus",
        "checker_model": "opus",        # HTML 审查用 opus（需要视觉模型分析）
        "depends": ["narration"],
        "parallel_group": "production",  # 与 tts 并行
        "max_retries": 3,
    },
    {
        "name": "tts",
        "maker_model": "opus",
        "checker_model": "haiku",
        "depends": ["narration"],
        "parallel_group": "production",  # 与 html 并行
        "max_retries": 3,
    },
    {
        "name": "assembly",
        "maker_model": "opus",
        "checker_model": "opus",        # 成品审查用 opus
        "depends": ["html", "tts"],
        "parallel_group": None,
        "max_retries": 3,
    },
    {
        "name": "publish",
        "maker_model": "haiku",
        "checker_model": "haiku",
        "depends": ["assembly"],
        "parallel_group": None,
        "max_retries": 3,
    },
]

# ═══════════════════════════════════════════════════════════════
# Token 预算（简单计数器）
# ═══════════════════════════════════════════════════════════════
TOKEN_BUDGET = 2_000_000   # 单视频硬上限 200 万 token
token_spent = 0


def spend_tokens(estimated: int) -> None:
    global token_spent
    token_spent += estimated
    if token_spent > TOKEN_BUDGET:
        raise RuntimeError(
            f"Token 预算耗尽: {token_spent:,} / {TOKEN_BUDGET:,}\n"
            f"请检查是否进入无限重试循环。"
        )


# ═══════════════════════════════════════════════════════════════
# 主编排逻辑
# ═══════════════════════════════════════════════════════════════

def run_stage(stage: dict, brief: str, output_dir: str = "") -> bool:
    """运行单个阶段: maker → checker → retry 循环。

    Returns:
        True: 阶段通过
        False: 重试耗尽，需人工介入
    """
    name = stage["name"]
    maker_model = stage["maker_model"]
    checker_model = stage["checker_model"]
    max_retries = stage["max_retries"]

    # --resume 时注入上次 FAIL 的上下文，让 Maker 知道为什么失败
    feedback = None
    prev = get_progress(name)
    if prev and "FAIL" in prev:
        feedback = f"⚠️ 上一轮运行此阶段失败：{prev}\n请避免重复同样的错误。"
        print(f"📋 [{name}] 从 PROGRESS.md 恢复上次失败上下文: {prev[:100]}...")

    for attempt in range(max_retries + 1):
        label = f"第 {attempt + 1}/{max_retries + 1} 次" if max_retries > 0 else ""
        print(f"\n{'='*60}")
        print(f"🎬 [{name}] Maker 开始 {label}".strip())
        print(f"{'='*60}")

        # ── Maker ──
        maker_output = run_maker(name, brief=brief, feedback=feedback, model=maker_model)
        spend_tokens(50_000)  # rough estimate per maker call

        print(f"✅ [{name}] Maker 完成 ({len(maker_output)} 字符)")

        # ── 持久化 Maker 输出（进程崩溃可恢复）──
        _save_maker_output(name, maker_output, output_dir)

        # ── Checker (可选) ──
        if checker_model is None:
            # brief 阶段：保存 Production Brief 供下游阶段使用
            if name == "brief":
                save_brief(maker_output)
            _on_pass(name)
            return True

        print(f"🔍 [{name}] Checker 审查中...")
        verdict = run_checker(name, maker_output, brief=brief, model=checker_model)
        spend_tokens(20_000)  # rough estimate per checker call

        # ── 判定 ──
        c, h, m = verdict.get("critical", 0), verdict.get("high", 0), verdict.get("medium", 0)

        if verdict["verdict"] == "PASS":
            print(f"🛡️  [{name}] Checker: PASS (C={c}, H={h}, M={m})")
            _on_pass(name)
            return True

        # FAIL
        summary = verdict.get("summary", "")
        print(f"💥 [{name}] Checker: FAIL (C={c}, H={h}, M={m}) {summary}")

        if attempt >= max_retries:
            break  # 重试耗尽

        # 准备下一轮重试的反馈
        feedback = (
            f"上一轮审查未通过（第 {attempt + 1}/{max_retries + 1} 次）：\n"
            f"- CRITICAL: {c}, HIGH: {h}, MEDIUM: {m}\n"
            f"- 审查总结: {summary}\n\n"
            f"请针对性修复上述问题后重新生成。"
        )
        print(f"🔄 [{name}] 准备重试 ({attempt + 1}/{max_retries})...")

    # 所有重试耗尽
    _on_escalate(name, verdict)
    return False


def _on_pass(name: str) -> None:
    """阶段通过：保存状态。"""
    state_save(name, "PASS")
    print(f"🏆 [{name}] 阶段通过 ✓")


def _on_escalate(name: str, last_verdict: dict) -> None:
    """重试耗尽：记录失败 + 升级给用户。"""
    state_save(name, "FAIL", {
        "critical": last_verdict.get("critical", 0),
        "high": last_verdict.get("high", 0),
        "medium": last_verdict.get("medium", 0),
    })
    print(f"\n{'!'*60}")
    print(f"🚨 [{name}] 重试耗尽，需人工介入！")
    print(f"   CRITICAL: {last_verdict.get('critical', 0)}")
    print(f"   HIGH:     {last_verdict.get('high', 0)}")
    print(f"   MEDIUM:   {last_verdict.get('medium', 0)}")
    print(f"   总结: {last_verdict.get('summary', '无')}")
    print(f"   进度已保存到 PROGRESS.md，修复后可用 --resume 继续。")
    print(f"{'!'*60}")


def _save_maker_output(name: str, output: str, output_dir: str) -> None:
    """持久化 Maker 输出到磁盘。防止 Maker 跑完、Checker 崩溃时产物丢失。"""
    out_path = Path(output_dir) / "_maker_outputs" / f"{name}.txt"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(output, encoding="utf-8")
    print(f"💾 [{name}] Maker 输出已保存: {out_path}")


# ═══════════════════════════════════════════════════════════════
# 依赖解析 & 主循环
# ═══════════════════════════════════════════════════════════════

def deps_met(stage: dict) -> bool:
    """检查前置阶段是否全部完成。"""
    return all(is_complete(d) for d in stage["depends"])


def run_pipeline(topic: str, output_dir: str) -> bool:
    """主循环：按阶段顺序编排，支持并行和断点续跑。"""
    global token_spent
    token_spent = 0

    print(f"\n{'#'*60}")
    print(f"# Loop Engineering 视频制作编排器")
    print(f"# 选题: {topic}")
    print(f"# 输出: {output_dir}")
    print(f"# Token 预算: {TOKEN_BUDGET:,}")
    print(f"{'#'*60}")

    # ── 初始化或恢复状态 ──
    if not get_topic():
        state_init(topic, output_dir)

    existing_topic = get_topic()
    if existing_topic and existing_topic != topic:
        print(f"⚠️  PROGRESS.md 中已有选题 '{existing_topic}'，与当前 '{topic}' 不同。")
        print(f"   如需开始新选题，请先删除 PROGRESS.md 和 PRODUCTION_BRIEF.md。")
        return False

    # ── 按组编排：同 parallel_group 的阶段并发执行 ──
    i = 0
    while i < len(STAGES):
        stage = STAGES[i]

        # 跳过已完成
        if is_complete(stage["name"]):
            print(f"⏭️  [{stage['name']}] 已完成，跳过")
            i += 1
            continue

        # 检查依赖
        if not deps_met(stage):
            missing = [d for d in stage["depends"] if not is_complete(d)]
            print(f"⏳ [{stage['name']}] 等待前置: {missing}")
            i += 1
            continue

        # ── 并行组 ──
        group = stage.get("parallel_group")
        if group:
            # 收集同组的所有阶段
            group_stages = [stage]
            j = i + 1
            while j < len(STAGES) and STAGES[j].get("parallel_group") == group:
                if deps_met(STAGES[j]) and not is_complete(STAGES[j]["name"]):
                    group_stages.append(STAGES[j])
                j += 1

            if len(group_stages) > 1:
                names = [s["name"] for s in group_stages]
                print(f"\n⚡ 并行执行: {names}")
                brief = get_brief()

                with ThreadPoolExecutor(max_workers=len(group_stages)) as executor:
                    futures = {
                        executor.submit(run_stage, s, brief, output_dir): s["name"]
                        for s in group_stages
                    }
                    all_pass = True
                    for future in as_completed(futures):
                        sname = futures[future]
                        try:
                            if not future.result():
                                all_pass = False
                                print(f"❌ [{sname}] 并行阶段失败，继续执行其他并行任务...")
                        except Exception as e:
                            all_pass = False
                            print(f"❌ [{sname}] 异常: {e}")

                    if not all_pass:
                        print("\n❌ 并行阶段失败，终止流水线。")
                        return False

                i = j
                continue

        # ── 串行阶段 ──
        brief = get_brief() if stage["name"] != "brief" else ""
        try:
            result = run_stage(stage, brief, output_dir)
            if not result:
                return False  # escalate
        except Exception as e:
            print(f"\n❌ [{stage['name']}] 异常退出: {e}")
            state_save(stage["name"], "FAIL", {"summary": str(e)})
            return False

        i += 1

    # ── 验证最终产物 ──
    final_video = Path(output_dir) / "output" / "final.mp4"
    if not final_video.exists() or final_video.stat().st_size == 0:
        print(f"\n❌ assembly 阶段声称完成，但 {final_video} 不存在或为空。")
        return False

    # ── 全部完成 ──
    print(f"\n{'#'*60}")
    print(f"# 🎉 全流程完成！")
    print(f"# Token 消耗: {token_spent:,} / {TOKEN_BUDGET:,}")
    print(f"# 视频输出: {final_video} ({final_video.stat().st_size / 1024 / 1024:.1f} MB)")
    print(f"{'#'*60}")
    return True


# ═══════════════════════════════════════════════════════════════
# CLI 入口
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Loop Engineering 视频制作编排器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python orchestrator.py "大语言模型的工作原理"
  python orchestrator.py --resume
  python orchestrator.py --topic "Prompt Engineering入门" --output scripts/prompt-eng
        """,
    )
    parser.add_argument("topic", nargs="?", help="视频选题标题")
    parser.add_argument("--resume", action="store_true", help="从 PROGRESS.md 断点续跑")
    parser.add_argument("--output", dest="output_dir", default=None,
                        help="输出目录（默认: scripts/{topic简写}）")
    parser.add_argument("--dry-run", action="store_true",
                        help="只打印阶段列表和依赖关系，不实际执行")

    args = parser.parse_args()

    # ── dry-run ──
    if args.dry_run:
        print("阶段依赖图:\n")
        for s in STAGES:
            deps = " → ".join(s["depends"]) if s["depends"] else "（无依赖）"
            checker = s["checker_model"] or "跳过"
            parallel = f" ⚡并行组: {s['parallel_group']}" if s.get("parallel_group") else ""
            print(f"  [{s['name']}] maker={s['maker_model']}, checker={checker}, "
                  f"retries={s['max_retries']}, 依赖: {deps}{parallel}")
        return

    # ── resume ──
    if args.resume:
        topic = get_topic()
        output_dir = get_output_dir()
        if not topic:
            print("❌ 未找到 PROGRESS.md，无法断点续跑。请先指定选题启动。")
            sys.exit(1)
        print(f"📂 断点续跑: {topic} → {output_dir}")
    else:
        topic = args.topic
        if not topic:
            print("❌ 请指定视频选题。用法: python orchestrator.py \"选题标题\"")
            sys.exit(1)
        output_dir = args.output_dir or f"scripts/{_slugify(topic)}"

    # ── 创建输出目录 ──
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    for sub in ["frames", "audio", "output"]:
        Path(output_dir, sub).mkdir(parents=True, exist_ok=True)

    def on_interrupt(signum, frame):
        print("\n\n⚠️  收到中断信号，正在退出...")
        print("   已完成阶段的进度已保存，可用 --resume 继续。")
        # os._exit 立即终止整个进程（包括子进程），
        # 不用 sys.exit 因为 ThreadPoolExecutor.shutdown 会等待 subprocess 结束
        os._exit(1)

    signal.signal(signal.SIGINT, on_interrupt)

    start_time = time.time()
    try:
        success = run_pipeline(topic, output_dir)
    except KeyboardInterrupt:
        print("\n⚠️  用户中断。已完成阶段进度已保存。")
        sys.exit(1)

    elapsed = time.time() - start_time

    print(f"\n⏱️  总耗时: {elapsed/60:.1f} 分钟")

    if not success:
        print("❌ 编排器异常退出。检查上方错误信息。")
        sys.exit(1)


def _slugify(text: str) -> str:
    """选题标题转安全的目录名（避开 ffmpeg 中文路径 bug）。

    '大语言模型的工作原理' → 'video-20260702-001'
    规则: 'video-' + 日期 + '-' + 自增序号（避免中文路径导致 ffmpeg 失败）
    """
    if not text or not text.strip():
        raise ValueError("选题标题不能为空")
    import datetime
    date = datetime.date.today().strftime("%Y%m%d")
    # 查找当天已有目录数，自增序号
    scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
    existing = list(scripts_dir.glob(f"video-{date}-*"))
    seq = len(existing) + 1
    return f"video-{date}-{seq:03d}"


if __name__ == "__main__":
    main()
