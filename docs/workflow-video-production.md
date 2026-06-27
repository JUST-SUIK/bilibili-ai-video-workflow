# 视频制作工作流 — 标准流程与避坑指南

> 每次制作视频都必须遵循此文档。遇到新问题后，必须回来更新。

---

## 一、标准流程

```
1. 脚本撰写 → 2. 画面设计(HTML) → 3. 视觉审查 → 4. 音频合成 → 5. 视频录制 → 6. 合并输出 → 7. 最终审查
```

**每个步骤完成后才能进入下一步。视觉审查不通过不能进入音频合成。**

---

## 二、画面设计（HTML）规范

### 2.1 必须遵守的设计原则

| 规则 | 说明 | 反面教材 |
|------|------|----------|
| **全片统一暗色风格** | 所有页面必须使用暗色背景，禁止出现白色/浅色页面 | 从漆黑房间突然转到明亮操场，观众眼睛受不了 |
| **字体最小 18px** | 在 1920×1080 分辨率下，任何文字不得小于 18px | 13px 的小字在屏幕上几乎看不见 |
| **颜色对比度 ≥ 4.5:1** | 文字颜色与背景的对比度必须达到 WCAG AA 标准 | 灰色文字在暗底上模糊不清 |
| **内容不重叠** | 任何元素不得被其他元素遮挡 | 副标题被标题卡片压在底下 |
| **动画延迟匹配音频** | 文字动画的出现时间必须与音频朗读节奏对齐 | 音频还没念到，文字已经全部显示了 |
| **禁止 Inter 字体** | 使用 Geist、Noto Sans SC 等字体 | Inter 在某些渲染下有字重变化导致"抖动" |

### 2.2 动画同步规则

**问题**：文字动画在页面加载时立即播放，但音频还没开始念。

**解决方案**：
- 引导语（如"一个反直觉的事实"）：0.5s 延迟出现
- 主体文字：延迟 3-5s，等引导语念完再开始逐字出现
- 数字/强调元素：延迟 7-10s，等主体文字念完再出现
- 底部信息：延迟 10s+

**公式**：`动画延迟 = 前一段音频时长 + 0.5s 缓冲`

### 2.3 每个页面必须有的元素

```
- 顶部标签（FRAME XX · 主题）  ← 15px，rgba(255,255,255,0.3)
- 主体内容                     ← 24px+，清晰可读
- 底部时间码                   ← 可选
```

---

## 三、视觉审查规范

### 3.1 必须使用视觉审查技能

**每次修改 HTML 页面后，必须使用 `visual-review` 技能进行审查。**

审查流程：
1. 截图所有 HTML 页面
2. 用 MiMo v2.5 视觉模型审查每张截图
3. 通过 → 继续；不通过 → 修复 → 重新审查
4. 最多 5 次，5 次仍未通过 → 报给用户

### 3.2 使用方式

```bash
MIMO_API_KEY="你的key" python ~/.claude/skills/visual-review/review.py --html "frames/*.html" --output "screenshots/report.md"
```

### 3.3 审查维度

| 维度 | 检查内容 |
|------|----------|
| 可见性 | 文字是否清晰可读，对比度是否足够 |
| 风格一致性 | 是否全片统一暗色风格，有无突兀亮色 |
| 字体大小 | 是否有小于 18px 的文字 |
| 布局 | 内容是否充分利用空间，有无过大空白 |
| 内容重叠 | 有无文字被遮挡 |
| 美观度 | 有无"糊成一坨"的区域 |

---

## 四、音频合成规范

### 4.1 音色选择

**必须使用 `mimo-v2.5-tts-voicedesign` 模型，不要用预置音色。**

音色描述模板：
```
用[口音]口音，语速[快/中]，像[场景描述]，带着[情绪]，[个性特点]。
```

示例（知识分享类）：
```
用山东口音，语速快，像朋友聊天一样分享好消息，带着兴奋和真诚，不做作。
```

### 4.2 音频间隔

**每段音频结尾必须添加 1-2 秒静音**，用于：
- 转场过渡
- 让观众消化信息
- 避免两段音频紧贴在一起

```python
silence = b'\x00\x00' * int(framerate * 1.5)  # 1.5秒静音
```

### 4.3 API 调用规范

**禁止在命令行中明文使用 API Key。** 使用环境变量：

```bash
MIMO_API_KEY="your_key" python script.py
```

或在脚本中：
```python
api_key = os.environ.get("MIMO_API_KEY")
```

---

## 五、视频录制规范

### 5.1 白屏问题

**问题**：Playwright 录制时，页面加载前会显示白色背景，导致视频开头有"白屏闪光弹"。

**解决方案**：在 browser context 中设置 `color_scheme="dark"`：

```python
context = browser.new_context(
    viewport={"width": 1920, "height": 1080},
    color_scheme="dark",  # ← 必须加
    record_video_dir=str(output_dir),
    record_video_size={"width": 1920, "height": 1080},
)
```

### 5.2 动画冻结

录制截图时，必须冻结动画，等字体加载完成后再解冻：

```python
page.add_init_script("""
    const s = document.createElement('style');
    s.id = '__pw_freeze';
    s.textContent = '*, *::before, *::after { animation-play-state: paused !important; }';
    document.documentElement.appendChild(s);
""")
# ... 等待页面加载 ...
page.evaluate("document.fonts.ready")
page.wait_for_timeout(1500)
page.evaluate("document.getElementById('__pw_freeze')?.remove()")
page.wait_for_timeout(500)
```

### 5.3 字体渲染一致性

**问题**：某些字体在 Playwright 渲染时会出现轻微"抖动"（字重/位置变化）。

**解决方案**：
- 禁止使用 Inter 字体（渲染不稳定）
- 使用 Geist、Noto Sans SC、Space Grotesk 等稳定字体
- 录制前确保字体完全加载（`document.fonts.ready`）

---

## 六、合并输出规范

### 6.1 中文路径问题

**问题**：ffmpeg 在中文路径下调用失败（WinError 193 或编码错误）。

**解决方案**：将文件复制到无中文的临时目录处理，完成后复制回来：

```python
import shutil, tempfile
tmp_dir = tempfile.mkdtemp(prefix="video_merge_")
shutil.copy2(str(video_path), os.path.join(tmp_dir, "video.webm"))
shutil.copy2(str(audio_path), os.path.join(tmp_dir, "audio.wav"))
# ... ffmpeg 处理 ...
shutil.copy2(os.path.join(tmp_dir, "output.mp4"), str(output_path))
shutil.rmtree(tmp_dir, ignore_errors=True)
```

### 6.2 ffmpeg 使用

使用 `imageio-ffmpeg` 自带的 ffmpeg 二进制，不要依赖系统 ffmpeg：

```python
import imageio_ffmpeg
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
```

---

## 七、已知问题清单

| 问题 | 状态 | 解决方案 |
|------|------|----------|
| 白屏闪光弹 | ✅ 已修复 | `color_scheme="dark"` |
| 文字动画与音频不同步 | ✅ 已修复 | 延迟动画匹配音频节奏 |
| 文字重叠 | ✅ 已修复 | 调整 `top` 位置 |
| 字体太小 | ✅ 已修复 | 最小 18px |
| 颜色对比度不足 | ✅ 已修复 | 提高文字亮度 |
| 蓝白页面与暗色风格冲突 | ✅ 已修复 | 统一暗色主题 |
| 音频无情感 | ✅ 已修复 | voicedesign + 性格描述 |
| 音频间隔太短 | ✅ 已修复 | 添加 1.5s 静音 |
| API Key 明文暴露 | ✅ 已修复 | 使用环境变量 |
| 中文路径 ffmpeg 失败 | ✅ 已修复 | 临时目录处理 |
| Inter 字体渲染抖动 | ✅ 已修复 | 改用 Geist 字体 |
| 无视觉审查流程 | ✅ 已修复 | 创建 visual-review 技能 |

---

## 八、更新日志

- **2026-06-28**：初版，记录视频制作全流程和已知问题解决方案
