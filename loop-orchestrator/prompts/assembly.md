合成最终视频。

## 步骤
1. 将每个HTML帧渲染为视频片段（Playwright录制+ffmpeg编码）
2. 按画面顺序拼接视频片段
3. 为每段添加对应TTS音频
4. 确保音画同步（音频对准画面起点）
5. 添加画面间转场
6. 从旁白文本生成字幕
7. 导出最终视频

## ⚠️ 技术规范（强制执行，来自踩坑记录）
- **Playwright必须设置 color_scheme="dark"** — 防止白屏闪光弹
- **中文路径用临时目录** — ffmpeg不支持中文路径，复制到temp处理后复制回来
- **使用 imageio-ffmpeg** — 不依赖系统ffmpeg：`import imageio_ffmpeg; FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()`
- **动画冻结** — 录制前冻结CSS动画，等字体加载完再解冻
- 详细规范参考 scripts/[视频名]/merge.py

## 输出参数
- 1920×1080, 30fps, H.264, AAC 128kbps
- 输出：scripts/[视频名]/output/final.mp4

## 输出清单
- 最终视频路径和总时长
- 音画同步检查报告
- 各段衔接流畅度

完成后标注：ASSEMBLY_COMPLETE。

重试时只修复审查标注的问题段落/时间点。