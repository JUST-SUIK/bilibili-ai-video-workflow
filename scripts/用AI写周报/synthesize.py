"""
MiMo TTS 合成脚本 - 用AI写周报
使用 mimo-v2.5-tts-voicedesign 模型，通过音色描述生成语音
API密钥通过环境变量 MIMO_API_KEY 读取，不硬编码
"""
import base64, os, sys, time

# ═══════ 配置 ═══════
API_KEY = os.environ.get("MIMO_API_KEY")
if not API_KEY:
    print("错误: 未设置 MIMO_API_KEY 环境变量")
    sys.exit(1)

# tp- 开头的 key 用 token-plan endpoint
if API_KEY.startswith("tp-"):
    BASE_URL = "https://token-plan-cn.xiaomimimo.com/v1"
else:
    BASE_URL = "https://api.xiaomimimo.com/v1"

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "audio")
# ═══════════════════════════════════════════════════════════════

from openai import OpenAI

client = OpenAI(
    api_key=API_KEY,
    base_url=BASE_URL,
)

# 音色描述（必须有个性，不能像念稿）
VOICE_DESC = "用山东口音，语速快，像朋友聊天一样分享好消息，带着兴奋和真诚，不做作。"

# ═══════ 7段旁白文本 ═══════
scripts = [
    # 01: 钩子 - 反直觉的事实
    """我跟你说一个反直觉的事实：用AI写周报，真正花时间的不是"写"，是"想"。你以为AI能帮你从零写周报？不能。但它能帮你把"想"的时间，从两小时压缩到十分钟。""",

    # 02: 痛点 - 写周报的痛苦
    """我猜你肯定经历过这种场景。周五下午四点，你打开电脑，准备写周报。然后你开始回忆：这周到底干了啥？周一好像开了个会，但具体讨论啥来着？周三那个方案，是改了两版还是三版？你翻聊天记录，翻邮件，翻日历。花了半小时，终于凑齐了素材。然后你开始写。写着写着，发现有个词不对。"改了几个bug"——太low了，领导看了会觉得我一周就干了这点事。改成"修复了多个系统漏洞，提升了稳定性"——嗯，这个听起来专业。但你又觉得太假了。这种纠结，每周都要来一次。最崩溃的是，你花了一个小时写完，领导扫一眼就过了。你心想：我这一小时，到底图啥？""",

    # 03: 核心方案1 - AI写周报的正确姿势
    """好，痛点说完了，我们来说解决方案。但我要先告诉你一个很多人不知道的事：AI写周报，不是让它"帮你写"。是让它"帮你润色"。什么意思？你不能直接跟AI说："帮我写本周周报。"它不知道你这周干了啥。你得先告诉它。所以正确的流程是：第一步，你自己花五分钟，快速回忆这周做了什么。用关键词就行，不用写完整句子。比如：周一开会、周三交付方案、帮同事解决问题。这五分钟，省不了。因为只有你知道这周发生了什么。""",

    # 04: 核心方案2 - 三个Prompt模板
    """好，素材整理完了，接下来就是见证奇迹的时刻。我给你三个Prompt模板，直接复制就能用。第一个：基础版。你把关键词丢给它，说："这是本周的工作记录，请帮我整理成周报。"它就会帮你组织成：工作内容、进展、下周计划。第二个：项目版。如果你这周主要在做某个项目，用这个。"这是XX项目的本周进展，请帮我写项目周报。"它会重点突出项目进度、遇到的问题、下一步计划。第三个：问题解决版。如果你这周解决了一个棘手问题，用这个。"我遇到了XX问题，这是解决过程，请帮我写成周报。"它会帮你写成：问题描述、解决步骤、结果、经验总结。三个模板，覆盖90%的周报场景。我现在给你演示一下。""",

    # 05: 核心方案3 - 实操演示
    """我们来实操一下。假设我这周的工作关键词是：周一，Q3目标会议；周三，交付产品方案V2；周四，帮小王解决服务器问题；周五，客户需求评审。我把这些丢给AI，用基础版模板。你看，十秒钟，它就给我生成了一段结构清晰的周报。然后我花两分钟检查一下，改几个词，搞定。整个过程，十分钟都用不了。""",

    # 06: 验证 - Before/After对比
    """光说不练假把式，我们来看Before和After。Before：自己写。"周一开会，周三交方案，周四帮同事解决问题。"流水账，领导看了想睡觉。After：AI润色后。"本周重点推进Q3目标对齐，完成产品方案V2交付，顺手帮同事解决了服务器问题。"同样的内容，但听起来专业多了。区别在哪？你负责"做了什么"，AI负责"怎么说"。你不用再纠结"改了几个bug"还是"修复漏洞"。你把事实告诉AI，它帮你包装。这就是AI写周报的正确用法。""",

    # 07: 总结 + CTA
    """好，我们来总结一下。AI写周报的核心就一句话：你负责回忆，AI负责表达。先把素材整理好，再让AI润色。三个Prompt模板，直接复制就能用。如果你觉得这个方法有用，点个收藏，下次写周报直接用。评论区告诉我，你平时写周报要多久？下期我讲怎么用AI写日报和月报，感兴趣的话点个关注。我们下期见。""",
]


def synthesize(text: str, frame_num: int):
    """合成单段语音"""
    print(f"\n[{frame_num:02d}/07] 正在合成... ({len(text)}字)")

    completion = client.chat.completions.create(
        model="mimo-v2.5-tts-voicedesign",
        messages=[
            {"role": "user", "content": VOICE_DESC},
            {"role": "assistant", "content": text}
        ],
        audio={"format": "wav"}
    )

    message = completion.choices[0].message
    audio_bytes = base64.b64decode(message.audio.data)

    # 在音频末尾添加1.5秒静音（自然停顿）
    import wave, io
    with wave.open(io.BytesIO(audio_bytes), 'rb') as w:
        params = w.getparams()
        frames = w.readframes(w.getnframes())
    # 生成1.5秒静音
    silence_frames = b'\x00\x00' * int(params.framerate * 1.5)
    filename = os.path.join(OUTPUT_DIR, f"{frame_num:02d}.wav")
    with wave.open(filename, 'wb') as out:
        out.setparams(params)
        out.writeframes(frames)
        out.writeframes(silence_frames)

    # 估算时长（含静音）
    duration = (len(frames) + len(silence_frames)) / (params.framerate * params.sampwidth)
    print(f"  -> {filename} ({len(audio_bytes)//1024}KB, ~{duration:.1f}秒)")
    print(f"  TTS_{frame_num:02d}_COMPLETE")
    return filename, duration


# ═══════ 执行 ═══════
os.makedirs(OUTPUT_DIR, exist_ok=True)

print("=" * 50)
print("MiMo TTS 音色设计合成 - 用AI写周报")
print(f"音色: {VOICE_DESC}")
print(f"输出目录: {OUTPUT_DIR}/")
print("=" * 50)

total_duration = 0
results = []

for i, text in enumerate(scripts):
    filename, duration = synthesize(text, i + 1)
    results.append({"frame": i + 1, "file": filename, "duration": round(duration, 1)})
    total_duration += duration
    time.sleep(0.5)  # 避免请求太快

print("\n" + "=" * 50)
print("ALL_TTS_COMPLETE")
print(f"总时长: ~{total_duration:.0f}秒 ({total_duration/60:.1f}分钟)")
print("\n音频时长明细:")
for r in results:
    print(f"  {r['file'].split(os.sep)[-1]}: {r['duration']:>5.1f}秒")
print(f"\n文件保存在: {OUTPUT_DIR}/")
