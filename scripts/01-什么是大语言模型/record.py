"""
Playwright 录制脚本：将 HTML 演示录制成 WebM 视频
用法：python record.py
"""
import os, time
from pathlib import Path
from playwright.sync_api import sync_playwright

# ═══════ 配置 ═══════
HTML_PATH = Path(__file__).parent / "frames" / "index.html"
OUTPUT_DIR = Path(__file__).parent / "video_output"
WIDTH, HEIGHT = 1920, 1080
FPS = 30
# ═══════════════════════════════════════════════════════════════

OUTPUT_DIR.mkdir(exist_ok=True)
video_path = OUTPUT_DIR / "presentation.webm"

print("=" * 50)
print("Playwright 视频录制")
print(f"HTML: {HTML_PATH}")
print(f"输出: {video_path}")
print("=" * 50)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)

    context = browser.new_context(
        viewport={"width": WIDTH, "height": HEIGHT},
        record_video_dir=str(OUTPUT_DIR),
        record_video_size={"width": WIDTH, "height": HEIGHT},
    )

    page = context.new_page()

    # 打开页面（带自动播放参数）
    file_url = HTML_PATH.as_uri() + "?autoplay=1"
    print(f"\n打开: {file_url}")
    page.goto(file_url, wait_until="networkidle")

    # 等待自动播放启动
    time.sleep(1)

    # 计算总时长
    total_duration = sum([11.5, 25.3, 29.9, 29.4, 35.2, 31.5, 22.4])
    print(f"总时长: {total_duration:.0f}秒 ({total_duration/60:.1f}分钟)")
    print("录制中...")

    # 等待自动播放完成
    # 每5秒检查一次，最多等总时长+30秒缓冲
    max_wait = total_duration + 30
    elapsed = 0
    while elapsed < max_wait:
        time.sleep(5)
        elapsed += 5
        done = page.evaluate("window.__autoPlayDone === true")
        remaining = max_wait - elapsed
        print(f"  {elapsed:.0f}s / {total_duration:.0f}s {'(完成)' if done else ''}")
        if done:
            break

    # 多等2秒让最后一页动画播完
    time.sleep(2)

    # 关闭并保存视频
    video_path_actual = page.video.path()
    context.close()
    browser.close()

    # 重命名视频文件
    final_path = OUTPUT_DIR / "presentation.webm"
    if video_path_actual and os.path.exists(video_path_actual):
        os.rename(video_path_actual, str(final_path))
        size = os.path.getsize(str(final_path))
        print(f"\n录制完成！")
        print(f"文件: {final_path} ({size//1024//1024}MB)")
    else:
        print(f"\n录制完成，文件在: {video_path_actual}")

print("\n下一步：合并音频")
print("运行: python merge.py")
