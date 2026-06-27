"""
MiMo TTS 声纹克隆批量合成脚本
使用 mimo-v2.5-tts-voiceclone 模型，基于参考音频复刻音色
"""
import base64, os, json, time

# ═══════ 配置 ═══════
API_KEY = os.environ.get("MIMO_API_KEY")
if not API_KEY:
    print("错误: 未设置 MIMO_API_KEY 环境变量")
    sys.exit(1)
BASE_URL = "https://api.xiaomimimo.com/v1"
REF_AUDIO_PATH = "reference_short.wav"  # 参考音频文件（裁剪后30秒）
OUTPUT_DIR = "audio_output"
NARRATION_FILE = "../narration.md"  # 讲稿文件
# ═══════════════════════════════════════════════════════════════

from openai import OpenAI

client = OpenAI(
    api_key=API_KEY,
    base_url=BASE_URL,
)

# 读取并编码参考音频
with open(REF_AUDIO_PATH, "rb") as f:
    ref_bytes = f.read()
ref_base64 = base64.b64encode(ref_bytes).decode("utf-8")

# 判断音频格式
ext = os.path.splitext(REF_AUDIO_PATH)[1].lower()
mime = "audio/mpeg" if ext in (".mp3",) else "audio/wav"
voice_data = f"data:{mime};base64,{ref_base64}"

# ═══════ 解析讲稿 ═══════
# 定义 7 段旁白文本（场景编号 = 文件名编号）
scripts = [
    # 场景1：钩子
    """你有没有想过一个问题：ChatGPT是怎么记住你前面说的话的？答案可能会让你意外——它根本没记住。每次你发消息给它，它都会把你之前说的所有内容，重新读一遍。""",

    # 场景2：痛点
    """我猜你肯定遇到过这种情况。你让AI帮你写个东西，它写出来了，但就是不对味。你改了改需求，它又给了一版新的，还是不对。来回五六次，你烦了，觉得这AI是不是听不懂人话。或者你问它一个很简单的问题，它给你回了一大段。看着挺专业，但仔细一看，全是正确的废话。你心想：这玩意儿到底有没有用啊？其实问题不在AI，问题在你对它的理解。你把它当成一个懂很多东西的人来对话，但它根本不是人。""",

    # 场景3：阅卷老师类比
    """好，我们先搞清楚一个最基本的问题：大语言模型到底在做什么？我给你打个比方。想象你是一个阅卷老师，面前有一份试卷。最后一道大题，学生只写了一半，没写完。你的任务是：把这个学生没写完的答案，补全。大语言模型做的事，跟这个一模一样。它不是一个知道答案的专家，它是一个看过几亿份试卷的阅卷老师。它根据你给它的内容，猜接下来最可能是什么。""",

    # 场景4：幻觉
    """现在你知道它在猜了。那问题来了：为什么它有时候猜得特别准，有时候又瞎猜？我再给你讲一个计算机里的概念，叫幻觉。不是它产生了幻觉，是它的机制决定了它必须编。你想啊，有些问题它在那些试卷里从来没见过。但它不能说我不知道。因为它的任务是补全、不是回答。所以它会编一个听起来像那么回事的答案。这就是为什么它会一本正经地胡说八道。不是它故意骗你，是它的机制决定了它必须说话，而且必须说得像那么回事。""",

    # 场景5：三个原则
    """好，搞清楚了原理，我们来说说怎么用。从刚才的原理，我能给你三个原则。第一，不要问它事实性问题。问它发生了什么，它大概率会编。但你让它帮我把这段话改得更专业，它很擅长。因为这是模式匹配，不是知识检索。第二，给它足够的上下文。它每次都把你之前说的话重新读一遍，所以你说得越清楚，它猜得越准。第三，别把它当专家，把它当实习生。你给它的指令越具体，它干得越好。这三个原则，是从原理推导出来的，不是网上抄的。""",

    # 场景6：对比演示
    """光说不练假把式，我给你演示一下。同样是让AI帮我写一段产品介绍。第一种写法：帮我写一个产品介绍。你看，它写出来了，但很泛，像模板。第二种写法：我是一个卖手工咖啡的店主，目标客户是上班族，他们注重品质但没时间。请帮我写一段产品介绍，语气要亲切但不油腻。你看，这次是不是好多了？区别在哪？第一种写法，它只能猜你想要什么。第二种写法，你告诉它了，它不用猜。这就是给上下文的力量。""",

    # 场景7：总结
    """好，我们来总结一下。大语言模型不是懂很多东西的人，它是一个看过几亿份试卷的阅卷老师。它的任务是猜、不是懂。它会编、因为它不能说我不知道。理解了这三点，你就超过了百分之九十的AI用户。记住：AI不是来取代你的，是来放大你的。但你得先懂它，它才能帮你。下一期，我讲怎么写Prompt。""",
]


def synthesize(text: str, frame_num: int):
    """合成单段语音"""
    print(f"\n[{frame_num}/7] 正在合成... ({len(text)}字)")

    completion = client.chat.completions.create(
        model="mimo-v2.5-tts-voiceclone",
        messages=[
            {"role": "user", "content": "用知识分享博主的语气，自然流畅，像一个朋友在聊天一样讲述。语速适中偏快，声音清晰有活力。"},
            {"role": "assistant", "content": text}
        ],
        audio={
            "format": "wav",
            "voice": voice_data
        }
    )

    message = completion.choices[0].message
    audio_bytes = base64.b64decode(message.audio.data)

    filename = f"{OUTPUT_DIR}/frame_{frame_num:02d}.wav"
    with open(filename, "wb") as f:
        f.write(audio_bytes)

    # 估算时长 (WAV: 24kHz 16bit mono → 48KB/s)
    duration = len(audio_bytes) / 48000
    print(f"  → {filename} ({len(audio_bytes)//1024}KB, ~{duration:.1f}秒)")
    return filename, duration


# ═══════ 执行 ═══════
os.makedirs(OUTPUT_DIR, exist_ok=True)

print("=" * 50)
print("MiMo TTS 声纹克隆批量合成")
print(f"参考音频: {REF_AUDIO_PATH}")
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
print("合成完成！")
print(f"总时长: ~{total_duration:.0f}秒 ({total_duration/60:.1f}分钟)")
print("\n时长明细:")
for r in results:
    print(f"  Frame {r['frame']:02d}: {r['duration']:>5.1f}秒")
print(f"\n文件保存在: {OUTPUT_DIR}/")
