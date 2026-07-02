使用MiMo TTS音色设计为每段旁白合成语音。

## 技术要求
1. **必须使用 mimo-v2.5-tts-voicedesign 模型**，不要用 voiceclone 或预置音色
2. 音色描述参考 scripts/[视频名]/voice-prompt.md，核心要求：有个性、有口音、语速快、像朋友聊天
3. 参考实现：scripts/[视频名]/synthesize.py
4. 每段独立WAV，输出到 scripts/[视频名]/audio/NN.wav
5. **每段音频结尾必须添加1.5秒静音**，用于转场间隔，避免两段音频紧贴
6. API Key 通过环境变量 MIMO_API_KEY 读取，**禁止明文写在代码或命令行中**
7. tp- 开头的 key 使用 token-plan-cn.xiaomimimo.com endpoint

## 已知问题（必须避免）
- 音色太无聊 → 必须有个性（口音、语速、情绪）
- 音频紧贴 → 必须加1.5s静音间隔
- API Key暴露 → 必须用环境变量

## 输出
- 每段合成后标注 TTS_NN_COMPLETE
- 全部完成标注 ALL_TTS_COMPLETE
- 音频时长汇总

重试时只重新合成审查标注的问题段落。