# -*- coding: utf-8 -*-
"""
Video merge script: render HTML frames to video and combine with audio
Usage: python merge.py
"""
import os
import subprocess
import wave
import tempfile
import shutil
import re
from pathlib import Path

# === Config ===
BASE = Path(__file__).parent
FRAMES_DIR = BASE / "frames"
AUDIO_DIR = BASE / "audio"
OUTPUT_DIR = BASE / "output"

# Audio durations per segment (seconds) - v4 山东口音 快语速
AUDIO_DURATIONS = {
    "01": 18.0,
    "02": 47.1,
    "03": 38.6,
    "04": 56.5,
    "05": 26.9,
    "06": 38.0,
    "07": 29.8,
}

# Transition duration (seconds)
TRANSITION_DURATION = 0.5

# Output params
WIDTH = 1920
HEIGHT = 1080
FPS = 30

# ffmpeg path
import imageio_ffmpeg
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
# ==============


def get_audio_duration(path):
    """Get audio file duration in seconds"""
    with wave.open(str(path), 'rb') as w:
        return w.getnframes() / w.getframerate()


def get_video_duration(video_path):
    """Get video duration in seconds"""
    try:
        cmd = [FFMPEG, "-i", str(video_path)]
        result = subprocess.run(cmd, capture_output=True, text=True)
        for line in result.stderr.split('\n'):
            if 'Duration' in line:
                match = re.search(r'Duration:\s*(\d+):(\d+):(\d+\.\d+)', line)
                if match:
                    h, m, s = match.groups()
                    return int(h) * 3600 + int(m) * 60 + float(s)
    except Exception:
        pass
    return None


def render_html_to_video(html_path, duration, output_webm):
    """Use Playwright video recording to render HTML to webm"""
    from playwright.sync_api import sync_playwright

    dur_str = f"{duration:.1f}"
    print(f"    recording HTML animation ({dur_str}s)...")

    tmp_dir = Path(tempfile.mkdtemp(prefix="pw_record_"))

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            # 暗色背景，防止白屏闪光
            context = browser.new_context(
                color_scheme="dark",
                viewport={"width": WIDTH, "height": HEIGHT},
                record_video_dir=str(tmp_dir),
                record_video_size={"width": WIDTH, "height": HEIGHT}
            )
            page = context.new_page()

            # 冻结动画，等字体加载完再播放
            page.add_init_script("""
                const s = document.createElement('style');
                s.id = '__pw_freeze';
                s.textContent = '*, *::before, *::after { animation-play-state: paused !important; }';
                (document.head || document.documentElement).appendChild(s);
            """)

            html_url = html_path.as_uri()
            page.goto(html_url)
            page.wait_for_load_state("networkidle")

            # 等字体加载完成
            page.evaluate("document.fonts.ready")
            page.wait_for_timeout(500)

            # 解冻动画
            page.evaluate("document.getElementById('__pw_freeze')?.remove()")

            # Wait for full audio duration + buffer
            wait_ms = int((duration + 1) * 1000)
            page.wait_for_timeout(wait_ms)

            video = page.video
            page.close()
            context.close()

            video.save_as(str(output_webm))
            browser.close()

        print(f"    recording done: {output_webm.name}")
        return True

    except Exception as e:
        print(f"    recording failed: {e}")
        return False
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def webm_to_mp4_with_audio(webm_path, audio_path, mp4_path, duration):
    """Combine webm video with audio into mp4"""
    print(f"    encoding mp4...")

    tmp_dir = Path(tempfile.mkdtemp(prefix="convert_"))

    try:
        tmp_webm = tmp_dir / "input.webm"
        tmp_audio = tmp_dir / "input.wav"
        tmp_mp4 = tmp_dir / "output.mp4"

        shutil.copy2(str(webm_path), str(tmp_webm))
        shutil.copy2(str(audio_path), str(tmp_audio))

        cmd = [
            FFMPEG, "-y",
            "-i", str(tmp_webm),
            "-i", str(tmp_audio),
            "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-c:a", "aac", "-b:a", "128k",
            "-pix_fmt", "yuv420p",
            "-r", str(FPS),
            "-t", str(duration),
            "-shortest",
            "-movflags", "+faststart",
            str(tmp_mp4)
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode == 0:
            shutil.copy2(str(tmp_mp4), str(mp4_path))
            size_kb = mp4_path.stat().st_size // 1024
            print(f"    done: {mp4_path.name} ({size_kb}KB)")
            return True
        else:
            print(f"    ffmpeg failed: {result.stderr[-500:]}")
            return False

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def concat_videos(video_paths, output_path):
    """Concat all video segments with transitions"""
    print("\nStep 2: Concatenating video segments...")

    tmp_dir = Path(tempfile.mkdtemp(prefix="concat_"))

    try:
        # Generate black transition clip
        transition_path = tmp_dir / "transition.mp4"
        dur_str = str(TRANSITION_DURATION)
        size_str = f"{WIDTH}x{HEIGHT}"
        cmd = [
            FFMPEG, "-y",
            "-f", "lavfi", "-i",
            f"color=c=black:s={size_str}:d={dur_str}:r={FPS}",
            "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-c:a", "aac", "-b:a", "128k",
            "-pix_fmt", "yuv420p",
            "-t", dur_str,
            str(transition_path)
        ]
        subprocess.run(cmd, capture_output=True, text=True)

        # Copy to tmp (avoid Chinese path issues)
        tmp_videos = []
        for i, vp in enumerate(video_paths):
            tmp_v = tmp_dir / f"seg_{i:02d}.mp4"
            shutil.copy2(str(vp), str(tmp_v))
            tmp_videos.append(tmp_v)

        # Create concat list
        concat_list = tmp_dir / "concat.txt"
        with open(concat_list, 'w', encoding='utf-8') as f:
            for i, tv in enumerate(tmp_videos):
                f.write(f"file '{tv}'\n")
                if i < len(tmp_videos) - 1:
                    f.write(f"file '{transition_path}'\n")

        tmp_output = tmp_dir / "final.mp4"

        cmd = [
            FFMPEG, "-y",
            "-f", "concat", "-safe", "0",
            "-i", str(concat_list),
            "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-c:a", "aac", "-b:a", "128k",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            str(tmp_output)
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode == 0:
            shutil.copy2(str(tmp_output), str(output_path))
            size_mb = output_path.stat().st_size // 1024 // 1024
            print(f"  concat done: {output_path} ({size_mb}MB)")
            return True
        else:
            print(f"  concat failed: {result.stderr[-500:]}")
            return False

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def generate_srt():
    """Generate SRT subtitles from narration.md"""
    print("\nStep 3: Generating subtitles...")
    narration_path = BASE / "narration.md"
    srt_path = OUTPUT_DIR / "subtitles.srt"

    if not narration_path.exists():
        print("  warning: narration.md not found, skipping")
        return None

    with open(narration_path, 'r', encoding='utf-8') as f:
        content = f.read()

    sections = re.split(r'## .*?(\d)', content)

    subtitle_entries = []
    current_time = 0.0
    index = 1

    for i in range(1, len(sections), 2):
        try:
            scene_num = int(sections[i])
        except (ValueError, IndexError):
            continue
        scene_text = sections[i + 1] if i + 1 < len(sections) else ""

        script_match = re.search(r'### .*?\n([\s\S]*?)(?=\n###|\n---|\Z)', scene_text)
        if not script_match:
            continue

        script = script_match.group(1).strip()
        lines = [line.strip().lstrip('>').strip() for line in script.split('\n')
                 if line.strip() and line.strip() != '>']
        lines = [l for l in lines if l]

        prefix = f"{scene_num:02d}"
        duration = AUDIO_DURATIONS.get(prefix, 30.0)
        segment_start = current_time

        chunk_size = max(1, len(lines) // max(1, int(duration / 8)))
        chunks = []
        for j in range(0, len(lines), chunk_size):
            chunk = '\n'.join(lines[j:j + chunk_size])
            if chunk.strip():
                chunks.append(chunk)

        if not chunks:
            current_time += duration + TRANSITION_DURATION
            continue

        chunk_duration = duration / len(chunks)

        for chunk in chunks:
            start = current_time
            end = current_time + chunk_duration - 0.1

            start_str = format_srt_time(start)
            end_str = format_srt_time(end)
            clean_text = chunk.replace('**', '').replace('*', '').strip()

            subtitle_entries.append(f"{index}\n{start_str} --> {end_str}\n{clean_text}\n")
            index += 1
            current_time += chunk_duration

        current_time = segment_start + duration + TRANSITION_DURATION

    with open(srt_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(subtitle_entries))

    print(f"  subtitles: {srt_path} ({len(subtitle_entries)} entries)")
    return srt_path


def format_srt_time(seconds):
    """Format SRT timestamp"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def main():
    """Main function"""
    print("=" * 60)
    print("Video Merge Script")
    print("=" * 60)

    OUTPUT_DIR.mkdir(exist_ok=True)

    tmp_dir = Path(tempfile.mkdtemp(prefix="video_merge_"))

    try:
        # === Step 1: Render each HTML frame to video segment ===
        print("\nStep 1: Rendering HTML frames to video segments...")
        video_segments = []

        for i in range(1, 8):
            prefix = f"{i:02d}"
            audio_path = AUDIO_DIR / f"{prefix}.wav"
            mp4_path = OUTPUT_DIR / f"segment_{prefix}.mp4"
            webm_path = tmp_dir / f"segment_{prefix}.webm"

            html_files = list(FRAMES_DIR.glob(f"{prefix}-*.html"))
            if not html_files:
                print(f"  error: {prefix}-*.html not found")
                return
            html_path = html_files[0]

            if not audio_path.exists():
                print(f"  error: {audio_path} not found")
                return

            duration = AUDIO_DURATIONS[prefix]
            dur_str = f"{duration:.1f}"
            print(f"\n  [{prefix}] {html_path.name}")
            print(f"  audio: {audio_path.name} ({dur_str}s)")

            # 1a. Record HTML animation with Playwright
            if not render_html_to_video(html_path, duration, webm_path):
                return

            # 1b. Combine webm with audio to mp4
            if not webm_to_mp4_with_audio(webm_path, audio_path, mp4_path, duration):
                return

            video_segments.append(mp4_path)

        # === Step 2: Concat all segments ===
        final_path = OUTPUT_DIR / "final.mp4"
        if not concat_videos(video_segments, final_path):
            return

        # === Step 3: Generate subtitles ===
        generate_srt()

        # === Done ===
        if final_path.exists():
            size_mb = final_path.stat().st_size // 1024 // 1024
            total_audio = sum(AUDIO_DURATIONS.values())
            total_transition = TRANSITION_DURATION * (len(AUDIO_DURATIONS) - 1)
            actual_duration = get_video_duration(final_path)

            print(f"\n{'=' * 60}")
            print("ASSEMBLY_COMPLETE")
            print(f"{'=' * 60}")
            print(f"output: {final_path}")
            print(f"size: {size_mb} MB")
            print(f"{'=' * 60}")

            print(f"\nSync report:")
            total_str = f"{total_audio:.1f}"
            trans_str = f"{total_transition:.1f}"
            expected_str = f"{total_audio + total_transition:.1f}"
            print(f"  audio total: {total_str}s")
            print(f"  transition total: {trans_str}s")
            print(f"  expected total: {expected_str}s")
            if actual_duration:
                actual_str = f"{actual_duration:.1f}"
                drift = abs(actual_duration - (total_audio + total_transition))
                drift_str = f"{drift:.1f}"
                status = "OK" if drift < 2.0 else "WARN"
                print(f"  actual total: {actual_str}s")
                print(f"  drift: {drift_str}s {status}")

            print(f"\nSegment check:")
            for i in range(1, 8):
                prefix = f"{i:02d}"
                seg = OUTPUT_DIR / f"segment_{prefix}.mp4"
                if seg.exists():
                    dur = get_video_duration(seg)
                    target = AUDIO_DURATIONS[prefix]
                    if dur:
                        drift = abs(dur - target)
                        drift_str = f"{drift:.1f}"
                        dur_str = f"{dur:.1f}"
                        target_str = f"{target:.1f}"
                        status = "OK" if drift < 1.0 else "WARN"
                        print(f"  [{prefix}] {dur_str}s / target {target_str}s {status} (drift {drift_str}s)")

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
