# -*- coding: utf-8 -*-
"""
Video merge v2: crossfade transitions between all segments.
Renders cover frame, combines all segments with xfade + acrossfade,
regenerates subtitles aligned to the new timeline.

Usage: python merge_v2.py
"""
import os
import subprocess
import wave
import tempfile
import shutil
import struct
import re
from pathlib import Path

# === Config ===
BASE = Path(__file__).parent
FRAMES_DIR = BASE / "frames"
AUDIO_DIR = BASE / "audio"
OUTPUT_DIR = BASE / "output"

# Segment info: (prefix, audio_duration_seconds)
# Cover has no audio; remaining segments match their audio durations.
SEGMENTS = [
    ("00", 3.0),   # cover, no audio
    ("01", 15.7),  # hook - v3
    ("02", 52.4),  # pain - v3
    ("03", 41.5),  # method - v3
    ("04", 61.5),  # templates - v3
    ("05", 29.7),  # demo - v3
    ("06", 43.6),  # comparison - v3
    ("07", 29.0),  # ending - v3
]

# Transition durations between consecutive segments
# Format: (src, dst, duration, transition_type)
# transition_type: "fade" = crossfade, "fadeblack" = fade to black then fade in
TRANSITIONS = [
    ("00", "01", 1.2, "fade"),      # cover -> hook (crossfade)
    ("01", "02", 0.8, "fade"),      # hook -> pain (both dark, crossfade OK)
    ("02", "03", 1.2, "fadeblack"), # pain -> method (dark->bright, use fadeblack!)
    ("03", "04", 0.8, "fade"),      # method -> templates (both bright, crossfade OK)
    ("04", "05", 0.8, "fade"),      # templates -> demo (light->dark, brief enough)
    ("05", "06", 0.8, "fade"),      # demo -> comparison (both dark, crossfade OK)
    ("06", "07", 0.8, "fade"),      # comparison -> ending (both dark, crossfade OK)
]

WIDTH = 1920
HEIGHT = 1080
FPS = 30

import imageio_ffmpeg
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
# ==============


def get_video_duration(video_path):
    """Get video duration in seconds via ffprobe/ffmpeg -i"""
    try:
        cmd = [FFMPEG, "-i", str(video_path)]
        r = subprocess.run(cmd, capture_output=True, encoding='utf-8', errors='replace')
        for line in r.stderr.split('\n'):
            if 'Duration' in line:
                m = re.search(r'Duration:\s*(\d+):(\d+):(\d+\.\d+)', line)
                if m:
                    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    except Exception:
        pass
    return None


def get_audio_duration(path):
    """Get WAV audio duration in seconds"""
    with wave.open(str(path), 'rb') as w:
        return w.getnframes() / w.getframerate()


def render_cover_to_video(html_path, duration, output_mp4):
    """Render cover HTML to MP4 with silent audio track using Playwright."""
    from playwright.sync_api import sync_playwright

    print(f"  [00] rendering cover HTML ({duration:.1f}s)...")
    tmp_dir = Path(tempfile.mkdtemp(prefix="pw_cover_"))

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            context = browser.new_context(
                viewport={"width": WIDTH, "height": HEIGHT},
                record_video_dir=str(tmp_dir),
                record_video_size={"width": WIDTH, "height": HEIGHT},
            )
            page = context.new_page()

            # 冻结所有动画，防止字体加载前动画就播完
            page.add_init_script("""
                const style = document.createElement('style');
                style.id = '__pw_freeze';
                style.textContent = '*, *::before, *::after { animation-play-state: paused !important; }';
                (document.head || document.documentElement).appendChild(style);
            """)

            page.goto(html_path.as_uri())
            page.wait_for_load_state("networkidle")

            # 等待所有字体加载完成
            page.evaluate("document.fonts.ready")
            page.wait_for_timeout(500)

            # 解冻动画
            page.evaluate("document.getElementById('__pw_freeze')?.remove()")

            wait_ms = int((duration + 1) * 1000)
            page.wait_for_timeout(wait_ms)

            video = page.video
            page.close()
            context.close()

            webm_path = tmp_dir / "cover.webm"
            video.save_as(str(webm_path))
            browser.close()

        # Generate silent WAV
        silent_wav = tmp_dir / "silence.wav"
        sample_rate = 24000
        num_frames = int(duration * sample_rate)
        with wave.open(str(silent_wav), 'wb') as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sample_rate)
            w.writeframes(b'\x00\x00' * num_frames)

        # Combine webm + silent audio into mp4
        tmp_mp4 = tmp_dir / "cover.mp4"
        cmd = [
            FFMPEG, "-y",
            "-i", str(webm_path),
            "-i", str(silent_wav),
            "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-c:a", "aac", "-b:a", "128k",
            "-pix_fmt", "yuv420p",
            "-r", str(FPS),
            "-t", str(duration),
            "-shortest",
            "-movflags", "+faststart",
            str(tmp_mp4),
        ]
        r = subprocess.run(cmd, capture_output=True, encoding='utf-8', errors='replace')
        if r.returncode == 0:
            shutil.copy2(str(tmp_mp4), str(output_mp4))
            print(f"  [00] done: {output_mp4.name}")
            return True
        else:
            print(f"  [00] ffmpeg failed: {r.stderr[-500:]}")
            return False

    except Exception as e:
        print(f"  [00] failed: {e}")
        return False
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def build_xfade_command(segment_paths, output_path):
    """
    Build and execute a single ffmpeg command using xfade (video) and
    acrossfade (audio) to combine all segments with crossfade transitions.

    segment_paths: list of 8 MP4 paths (cover + 01-07), all have audio tracks
    """
    n = len(segment_paths)
    print(f"\n  Building xfade filter chain for {n} segments...")

    # Compute segment durations from actual files
    durations = []
    for p in segment_paths:
        d = get_video_duration(p)
        if d is None:
            print(f"  ERROR: cannot read duration of {p}")
            return False
        durations.append(d)
        print(f"    {Path(p).name}: {d:.1f}s")

    # Compute xfade offsets
    # For chained xfade: each offset = cumulative_output_duration - transition_duration
    # cumulative starts as durations[0], then each xfade output = prev_cum + next_dur - trans_dur
    video_filters = []
    audio_filters = []
    cumulative_dur = durations[0]

    for i, (src, dst, trans_dur, trans_type) in enumerate(TRANSITIONS):
        offset = cumulative_dur - trans_dur
        if offset < 0:
            print(f"  WARNING: negative offset for {src}->{dst}, clamping to 0")
            offset = 0

        # Video xfade (supports different transition types)
        in_label = f"[{i}:v]" if i == 0 else f"[v{i-1}]"
        out_label = f"[v{i}]"
        video_filters.append(
            f"{in_label}[{i+1}:v]xfade=transition={trans_type}:duration={trans_dur}:offset={offset:.3f}{out_label}"
        )

        # Audio acrossfade
        audio_in = f"[{i}:a]" if i == 0 else f"[a{i-1}]"
        audio_out = f"[a{i}]"
        audio_filters.append(
            f"{audio_in}[{i+1}:a]acrossfade=d={trans_dur}:c1=tri:c2=tri{audio_out}"
        )

        cumulative_dur = cumulative_dur + durations[i + 1] - trans_dur
        print(f"    xfade {src}->{dst}: offset={offset:.3f}s, duration={trans_dur}s, type={trans_type}")

    print(f"  Expected output duration: {cumulative_dur:.1f}s")

    # Build filter_complex string
    fc = ";\n".join(video_filters + audio_filters)

    last_video = f"[v{n-2}]"
    last_audio = f"[a{n-2}]"

    tmp_dir = Path(tempfile.mkdtemp(prefix="xfade_"))

    try:
        # Copy all inputs to temp dir (avoid Chinese path issues)
        tmp_inputs = []
        for i, p in enumerate(segment_paths):
            tmp_p = tmp_dir / f"input_{i:02d}.mp4"
            shutil.copy2(str(p), str(tmp_p))
            tmp_inputs.append(tmp_p)

        tmp_output = tmp_dir / "output.mp4"

        cmd = [FFMPEG, "-y"]
        for tp in tmp_inputs:
            cmd += ["-i", str(tp)]
        cmd += [
            "-filter_complex", fc,
            "-map", last_video,
            "-map", last_audio,
            "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-c:a", "aac", "-b:a", "128k",
            "-pix_fmt", "yuv420p",
            "-r", str(FPS),
            "-movflags", "+faststart",
            str(tmp_output),
        ]

        print(f"\n  Running ffmpeg xfade merge...")
        print(f"  Filter complexity: {len(video_filters)} video + {len(audio_filters)} audio filters")

        r = subprocess.run(cmd, capture_output=True, encoding='utf-8', errors='replace')

        if r.returncode == 0:
            shutil.copy2(str(tmp_output), str(output_path))
            size_mb = output_path.stat().st_size // 1024 // 1024
            print(f"  Merge done: {output_path} ({size_mb}MB)")
            return True
        else:
            print(f"  ffmpeg FAILED (code {r.returncode})")
            # Print last 2000 chars of stderr for debugging
            stderr_tail = r.stderr[-2000:] if r.stderr else "(no stderr)"
            print(f"  stderr:\n{stderr_tail}")
            return False

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def generate_srt(segment_durations, transitions):
    """Generate SRT subtitles from narration.md, aligned to the new crossfade timeline.

    The cover segment (00) shifts the timeline by its duration minus the first transition.
    """
    print("\n  Generating subtitles...")
    narration_path = BASE / "narration.md"
    srt_path = OUTPUT_DIR / "subtitles_v2.srt"

    if not narration_path.exists():
        print("  warning: narration.md not found, skipping")
        return None

    with open(narration_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Parse narration sections
    # Format: ## 画面 N — title ... ### 讲稿\n> text...
    sections = re.split(r'## .*?(\d)\s*[—–-]', content)

    # Build a map of scene_number -> text lines
    scene_texts = {}
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
        scene_texts[scene_num] = lines

    # Compute timeline offsets for each segment after crossfade
    # The audio from segment 01 starts playing at time 0 (fade-in during cover->01 transition)
    # So subtitles for segment 01 start at 0.
    # Segment 02's audio starts at: d[0] + d[1] - t[0,1]
    # But actually, with acrossfade, the audio is blended. The effective start time
    # of each segment's content (after transition) is:
    #
    # cumulative_offset[i] = sum(d[0..i]) - sum(t[0..i-1]) - t[i-1]/2
    #
    # Simpler approach: subtitles should track the visual content, which appears
    # at the offset point. Let me compute the visual timeline:

    # Visual content timeline (when each segment is fully visible):
    # Segment 00 (cover): 0.0 - 1.5 (then fading into 01)
    # Segment 01: 1.5 (fully visible) - 14.9 (start fading into 02)
    # But actually with crossfade, the new segment starts appearing at offset
    # and is fully visible at offset + transition_duration.

    # For subtitles, we want them to appear when the corresponding visual is visible.
    # The audio for segment N starts being audible at cumulative_offset.

    # Let me compute cumulative offsets (when each segment's audio starts dominating):
    seg_durations = [d for _, d in segment_durations]
    trans_durations = [t for _, _, t, _ in transitions]

    # After the cover (3s) with 1.5s transition, segment 01's content is fully visible at 1.5s
    # The cumulative audio "start" for each segment:
    cumulative = 0.0
    segment_starts = [0.0]  # cover starts at 0
    for i in range(len(seg_durations) - 1):
        cumulative += seg_durations[i] - trans_durations[i]
        segment_starts.append(cumulative)

    # Subtitles start from segment 01 (skip cover which has no narration)
    subtitle_entries = []
    index = 1

    for scene_num in sorted(scene_texts.keys()):
        if scene_num < 1 or scene_num > 7:
            continue
        lines = scene_texts[scene_num]
        if not lines:
            continue

        # Segment start time in the final video
        # scene_num 1 = segment 01, which is index 1 in segment_starts
        seg_start = segment_starts[scene_num]  # scene_num matches segment index

        # Audio duration for this segment
        prefix = f"{scene_num:02d}"
        audio_dur = dict(SEGMENTS).get(prefix, 30.0)

        # Split lines into chunks (one subtitle per ~6-8 seconds of audio)
        chunk_size = max(1, len(lines) // max(1, int(audio_dur / 7)))
        chunks = []
        for j in range(0, len(lines), chunk_size):
            chunk = '\n'.join(lines[j:j + chunk_size])
            if chunk.strip():
                chunks.append(chunk)

        if not chunks:
            continue

        chunk_duration = audio_dur / len(chunks)
        current_time = seg_start

        for chunk in chunks:
            start = current_time
            end = current_time + chunk_duration - 0.1

            start_str = format_srt_time(start)
            end_str = format_srt_time(end)
            clean_text = chunk.replace('**', '').replace('*', '').strip()

            subtitle_entries.append(f"{index}\n{start_str} --> {end_str}\n{clean_text}\n")
            index += 1
            current_time += chunk_duration

    with open(srt_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(subtitle_entries))

    print(f"  subtitles: {srt_path} ({len(subtitle_entries)} entries)")
    return srt_path


def format_srt_time(seconds):
    """Format seconds to SRT timestamp HH:MM:SS,mmm"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def main():
    print("=" * 60)
    print("Video Merge v2 — Crossfade Transitions")
    print("=" * 60)

    OUTPUT_DIR.mkdir(exist_ok=True)

    tmp_dir = Path(tempfile.mkdtemp(prefix="merge_v2_"))

    try:
        # === Step 1: Ensure all segment MP4s exist ===
        print("\nStep 1: Checking segment files...")
        segment_paths = []

        for prefix, duration in SEGMENTS:
            mp4_path = OUTPUT_DIR / f"segment_{prefix}.mp4"

            if prefix == "00":
                # Cover segment — render from HTML if not exists
                html_files = list(FRAMES_DIR.glob(f"{prefix}-*.html"))
                if not html_files:
                    print(f"  ERROR: {prefix}-*.html not found in {FRAMES_DIR}")
                    return
                html_path = html_files[0]

                if not mp4_path.exists():
                    print(f"  [00] cover segment not found, rendering...")
                    if not render_cover_to_video(html_path, duration, mp4_path):
                        return
                else:
                    print(f"  [00] cover segment exists: {mp4_path.name}")
            else:
                # Audio segments — should already exist
                audio_path = AUDIO_DIR / f"{prefix}.wav"
                if not mp4_path.exists():
                    print(f"  ERROR: {mp4_path} not found. Run the original merge.py first to generate segments.")
                    return
                if not audio_path.exists():
                    print(f"  ERROR: {audio_path} not found.")
                    return
                print(f"  [{prefix}] segment exists: {mp4_path.name}")

            segment_paths.append(mp4_path)

        # === Step 2: Merge with xfade crossfade ===
        print("\nStep 2: Merging with crossfade transitions...")
        final_path = OUTPUT_DIR / "final_v2.mp4"

        if not build_xfade_command(segment_paths, final_path):
            print("\n  FAILED to build final video.")
            return

        # === Step 3: Generate subtitles ===
        print("\nStep 3: Generating subtitles...")
        generate_srt(SEGMENTS, TRANSITIONS)

        # === Step 4: Report ===
        if final_path.exists():
            actual_duration = get_video_duration(final_path)
            size_mb = final_path.stat().st_size // 1024 // 1024

            total_audio = sum(d for _, d in SEGMENTS if _ != "00")
            total_transition_time = sum(t for _, _, t, _ in TRANSITIONS)
            expected_duration = sum(d for _, d in SEGMENTS) - total_transition_time

            print(f"\n{'=' * 60}")
            print("ASSEMBLY_COMPLETE")
            print(f"{'=' * 60}")
            print(f"Output: {final_path}")
            print(f"Size: {size_mb} MB")
            print(f"{'=' * 60}")

            print(f"\nTransition schedule:")
            for src, dst, dur, _ in TRANSITIONS:
                print(f"  {src} -> {dst}: {dur}s crossfade")

            print(f"\nSync report:")
            print(f"  Audio segments total: {total_audio:.1f}s")
            print(f"  Cover duration: 3.0s")
            print(f"  Transition overhead: {total_transition_time:.1f}s")
            print(f"  Expected total: {expected_duration:.1f}s")
            if actual_duration:
                drift = abs(actual_duration - expected_duration)
                status = "OK" if drift < 2.0 else "WARN"
                print(f"  Actual total: {actual_duration:.1f}s")
                print(f"  Drift: {drift:.1f}s [{status}]")

            print(f"\nSegment check:")
            for prefix, target in SEGMENTS:
                seg = OUTPUT_DIR / f"segment_{prefix}.mp4"
                dur = get_video_duration(seg)
                if dur:
                    drift = abs(dur - target)
                    status = "OK" if drift < 1.0 else "WARN"
                    print(f"  [{prefix}] {dur:.1f}s / target {target:.1f}s [{status}] (drift {drift:.1f}s)")

            print(f"\nOutput specs:")
            print(f"  Resolution: {WIDTH}x{HEIGHT}")
            print(f"  FPS: {FPS}")
            print(f"  Codec: H.264 + AAC 128kbps")
            print(f"  Subtitles: {OUTPUT_DIR / 'subtitles_v2.srt'}")

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
