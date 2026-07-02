逐帧生成HTML动画文件。参考Production Brief了解模板列表。

## 技术要求
1. 每画面一个独立HTML，1920×1080
2. 内联CSS动画，调用 .agents/skills/ 下对应 frame-* 模板的SKILL
3. 每个HTML包含：进场动画+循环动画+画面内容
4. 风格统一（色调、字体），与旁白情绪匹配
5. 输出路径：scripts/[视频名]/frames/NN-name.html

## ⚠️ 设计规范（强制执行，来自踩坑记录）
- **全片统一暗色风格** — 禁止白色/浅色页面，所有背景 #0a0a0f ~ #0d0d14
- **字体最小18px** — 在1920×1080下小于18px不可读
- **禁止使用Inter字体** — Playwright录制时会抖动，用Geist或Noto Sans SC
- **动画延迟匹配音频** — 文字不能比旁白先出现，引导语0.5s，主体文字3-5s，数字7-10s
- **内容不重叠** — 任何元素不得被其他元素遮挡
- **颜色对比度≥4.5:1** — 文字与背景对比度必须达标
- 详细规范参考 scripts/[视频名]/style-guide.md

## 步骤（每帧）
1. 阅读对应的frame-* SKILL.md了解模板用法
2. 根据画面要点生成HTML
3. 标注FRAME_NN_COMPLETE

全部完成后标注：ALL_FRAMES_COMPLETE。

重试时只修复审查标注的问题帧，不要改动已通过的帧。