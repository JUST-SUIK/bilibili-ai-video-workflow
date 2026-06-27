# B站AI知识分享视频制作工作流

> 自动化B站知识分享视频的全流程制作：选题→脚本→HTML动画帧→TTS配音→视频合成→发布素材

## 项目结构

```
├── docs/                           # 项目文档
│   ├── 01-项目总览.md               # 账号定位和策略
│   ├── 02-选题方向.md               # 选题库（21个选题）
│   ├── 03-录音与声纹指南.md          # TTS流程
│   ├── 04-视频制作流程.md            # 技术路线
│   ├── 05-素材资源库.md              # 工具和素材
│   ├── 06-脚本大纲模板.md            # 脚本规范
│   ├── 研究-脚本写作方法论.md         # HPSV等方法论
│   └── workflow-video-production.md  # 踩坑记录和设计规范
├── workflows/                       # 工作流定义
│   └── bilibili-video-production.json
├── scripts/                         # 视频制作目录
│   └── [视频名]/
│       ├── frames/                  # HTML动画帧
│       ├── audio/                   # TTS音频
│       ├── output/                  # 最终视频
│       ├── script.md                # 视频脚本
│       ├── narration.md             # 旁白规划
│       ├── style-guide.md           # 视觉风格指南
│       ├── voice-prompt.md          # 音色设计提示词
│       ├── synthesize.py            # TTS合成脚本
│       └── merge.py                 # 视频合并脚本
├── skills/                          # 技能定义
└── examples/                        # 示例
```

## 快速开始

### 1. 环境准备

```bash
# Python 依赖
pip install openai playwright imageio-ffmpeg httpx

# Playwright 浏览器
playwright install chromium

# 设置 API Key
export MIMO_API_KEY="your_key_here"
```

### 2. 使用工作流

```bash
# 通过 Claude Code 运行工作流
# 工作流会自动编排：选题→脚本→HTML→TTS→合成→发布
```

### 3. 手动制作

```bash
cd scripts/[视频名]

# 合成 TTS 音频
python synthesize.py

# 合成视频
python merge.py
```

## 技术栈

- **HTML动画帧**：纯CSS动画，1920×1080，Playwright录制
- **TTS配音**：MiMo v2.5 TTS（音色设计模型）
- **视频合成**：Playwright + ffmpeg
- **视觉审查**：MiMo v2.5 视觉模型

## 设计规范

- 全片统一暗色风格
- 字体最小 18px
- 动画延迟匹配音频节奏
- 每段音频加 1.5s 静音间隔
- 禁止使用 Inter 字体

详见 `docs/workflow-video-production.md`

## 许可证

MIT
