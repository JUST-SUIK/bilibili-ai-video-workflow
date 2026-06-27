"""
音频合并脚本：将各场景音频拼接并与视频合并
用法：python merge.py
"""
import os, subprocess, wave
from pathlib import Path

# ═══════ 配置 ═══════
BASE = Path(__file__).parent
AUDIO_DIR = BASE / "audio_output"
VIDEO_DIR = BASE / "video_output"
import imageio_ffmpeg
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
FFPROBE = FFMPEG.replace("ffmpeg", "ffprobe")  # imageio-ffmpeg 没有 ffprobe，用 ffmpeg -i 代替

# 每段音频时长（秒），与 HTML 中的 SCENE_DURATIONS 对应
SCENE_DURATIONS = [11.5, 25.3, 29.9, 29.4, 35.2, 31.5, 22.4]
# ═══════════════════════════════════════════════════════════════

def get_audio_duration(path):
    """获取音频文件时长（秒）"""
    with wave.open(str(path), 'rb') as w:
        return w.getnframes() / w.getframerate()

def concat_audio_files():
    """将7段音频按顺序拼接成一个完整音频"""
    print("步骤1: 拼接音频文件")

    # 读取所有音频，记录实际时长
    all_frames = []
    sample_rate = None
    for i in range(1, 8):
        audio_path = AUDIO_DIR / f"frame_{i:02d}.wav"
        with wave.open(str(audio_path), 'rb') as w:
            if sample_rate is None:
                sample_rate = w.getframerate()
                channels = w.getnchannels()
                sampwidth = w.getsampwidth()
            frames = w.readframes(w.getnframes())
            all_frames.append(frames)
            actual_dur = len(frames) / (sample_rate * channels * sampwidth)
            print(f"  frame_{i:02d}.wav: {actual_dur:.1f}s (目标: {SCENE_DURATIONS[i-1]}s)")

    # 拼接所有音频
    output_path = VIDEO_DIR / "full_audio.wav"
    with wave.open(str(output_path), 'wb') as out:
        out.setnchannels(channels)
        out.setsampwidth(sampwidth)
        out.setframerate(sample_rate)
        for frames in all_frames:
            out.writeframes(frames)

    total_dur = get_audio_duration(output_path)
    print(f"  拼接完成: {total_dur:.1f}s -> {output_path}")
    return output_path

def merge_video_audio(audio_path):
    """将视频和音频合并为 MP4"""
    print("\n步骤2: 合并视频和音频")

    video_path = VIDEO_DIR / "presentation.webm"
    output_path = VIDEO_DIR / "final_video.mp4"

    if not video_path.exists():
        print(f"  错误: 视频文件不存在 {video_path}")
        return None

    # 获取视频时长（用 wave 获取音频时长作为参考）
    video_dur = get_audio_duration(audio_path)  # 用音频时长作为参考
    audio_dur = get_audio_duration(audio_path)
    print(f"  视频时长: {video_dur:.1f}s")
    print(f"  音频时长: {audio_dur:.1f}s")

    # 合并：视频 + 音频 → MP4
    # 如果音频比视频长，用 -shortest 截断；如果短，视频后面会静音
    # 复制到无中文路径避免编码问题
    import shutil, tempfile
    tmp_dir = tempfile.mkdtemp(prefix="video_merge_")
    tmp_video = os.path.join(tmp_dir, "video.webm")
    tmp_audio = os.path.join(tmp_dir, "audio.wav")
    tmp_output = os.path.join(tmp_dir, "output.mp4")
    shutil.copy2(str(video_path), tmp_video)
    shutil.copy2(str(audio_path), tmp_audio)

    cmd = [
        FFMPEG, "-y",
        "-i", tmp_video,
        "-i", tmp_audio,
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        "-movflags", "+faststart",
        tmp_output
    ]

    print(f"  编码中...")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode == 0:
        shutil.copy2(tmp_output, str(output_path))
        size = os.path.getsize(str(output_path))
        print(f"\n完成！")
        print(f"文件: {output_path}")
        print(f"大小: {size//1024//1024}MB")
    else:
        print(f"  错误: {result.stderr[-500:]}")

    # 清理临时目录
    shutil.rmtree(tmp_dir, ignore_errors=True)

    return output_path

# ═══════ 执行 ═══════
print("=" * 50)
print("视频 + 音频合并")
print("=" * 50)

audio_path = concat_audio_files()
merge_video_audio(audio_path)
