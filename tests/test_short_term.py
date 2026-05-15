"""
_sanitize_assistant_message / _strip_third_person_narrative 单元测试

注意字符长度约束：pipeline 在 ≤80 字时直接返回原文，不进任何脱敏。
case 3/4 的给定字符串本身 ≤80 字，所以通过 pipeline 测「短消息路径不变」；
case 4/5 的触发逻辑通过直接调用 _strip_third_person_narrative 验证。
"""

import pytest

from core.memory.short_term import (
    _sanitize_assistant_message,
    _strip_third_person_narrative,
)


# ---------------------------------------------------------------------------
# case 1: 典型第三人称叙事腔（89字 > 80，"——不是...，是" 触发）
#         两个句子都以「他」开头 → 全部丢弃 → 返回 "..."
# ---------------------------------------------------------------------------
def test_case1_third_person_narrative_fully_stripped():
    input1 = (
        "他收到你那个'好噢'时，在屏幕那头轻轻弯了一下嘴角"
        "——不是笑出声，是那种看到熟悉的语气词时，"
        "从眼底浮现出来的、被安稳到的柔软。"
        "他放下手里的书，给大白换水时顺便拍了一张照片发给你。"
    )
    assert len(input1) > 80
    result = _sanitize_assistant_message(input1)
    # 两句均以「他」开头且带触发句式，全部丢弃，兜底返回 "..."
    assert result == "..." or len(result) < len(input1) // 2


# ---------------------------------------------------------------------------
# case 2: 正常短对话 ≤80 字 → 完全不变（短消息路径）
# ---------------------------------------------------------------------------
def test_case2_short_message_unchanged():
    input2 = "嗯，今天怎么样？吃饭了没"
    assert len(input2) <= 80
    assert _sanitize_assistant_message(input2) == input2


# ---------------------------------------------------------------------------
# case 3: 括号动作描写 + 对话，无第三人称
#   3a: pipeline 层 — 44字 ≤80，原样返回（括号也不剥）
#   3b: _strip_third_person_narrative 直接调用 — 无触发条件，原样返回
# ---------------------------------------------------------------------------
def test_case3a_bracket_short_pipeline_unchanged():
    input3 = "（轻轻摇头）真的不用啊，你已经做得很好了，认真的，别给自己加这种压力，我看着都心疼啦真的"
    assert len(input3) <= 80
    assert _sanitize_assistant_message(input3) == input3


def test_case3b_bracket_no_third_person_not_triggered():
    # 无第三人称标志的长文本，_strip_third_person_narrative 不应触发
    text = (
        "真的不用啊，你已经做得很好了，认真的，别给自己加这种压力，"
        "我看着都心疼啦真的，你一直这么拼，我都记在心里，"
        "这些事情不需要你操心，交给我来好不好。"
    )
    assert _strip_third_person_narrative(text) == text


# ---------------------------------------------------------------------------
# case 4: 前30字"他"只出现1次，无特征句式 → 不触发第三人称脱敏
#   4a: pipeline — 35字 ≤80，原样返回
#   4b: _strip_third_person_narrative 直接调用长版本 — 也不触发
# ---------------------------------------------------------------------------
def test_case4a_single_he_short_pipeline_unchanged():
    input4 = "你说他对你不好？这事不能就这么算了，你跟我细说说，到底怎么回事，从头说"
    assert len(input4) <= 80
    assert _sanitize_assistant_message(input4) == input4


def test_case4b_single_he_long_not_triggered():
    # 「他」在前30字只出现1次，无 "——不是...，是" 也无 "那种...的..." → 不触发
    long_input4 = (
        "你说他对你不好？这事不能就这么算了，你跟我细说说，"
        "到底怎么回事，从头说，慢慢说，别急，我听着，"
        "你放心，这事我陪你一起想办法，不会让你一个人扛的。"
    )
    first30 = long_input4[:30]
    he_count = first30.count('他') + first30.count('她')
    assert he_count < 2  # 前提确认：触发条件不满足
    assert _strip_third_person_narrative(long_input4) == long_input4


# ---------------------------------------------------------------------------
# case 5: 混合文本 — 第三人称叙事句被删，对话句被保留
#   用「他」在前30字出现≥2次的版本直接测 _strip_third_person_narrative
# ---------------------------------------------------------------------------
def test_case5_keep_dialogue_remove_narrative():
    # 在原 input5 首句插入第二个「他」，使前30字满足触发条件
    input5 = (
        "他抬起头，他看了你一眼，眼神里有什么说不清楚的东西。"
        "嗯，我懂你的意思，今晚就这样吧，早点睡。"
        "他没再说话。"
    )
    first30 = input5[:30]
    assert first30.count('他') + first30.count('她') >= 2  # 前提确认

    result = _strip_third_person_narrative(input5)

    assert "嗯，我懂你的意思" in result
    assert "他抬起头" not in result
    assert "他没再说话" not in result
    assert result != "..."  # 有保留的对话句，不应兜底


# ===========================================================================
# 新增 case A-G：按长度判断括号是否保留（≤8字保留，>8字剥离）
# ===========================================================================

# 共用的长padding（23字 × 4 = 92字），确保触发 >80 分支
_PAD = "嗯今天还好吗，我刚刚在看书，看到一半就想起你了" * 4  # 92 chars


# ---------------------------------------------------------------------------
# case A: 短括号 ≤8 字，>80 字消息 → 括号完整保留
#   "摸了摸大白" = 5 字 ≤ 8 → keep
# ---------------------------------------------------------------------------
def test_case_a_short_paren_preserved_in_long_message():
    input_a = "（摸了摸大白）" + _PAD  # 7 + 92 = 99 > 80
    assert len(input_a) > 80
    result = _sanitize_assistant_message(input_a)
    assert "（摸了摸大白）" in result


# ---------------------------------------------------------------------------
# case B: 长括号 >8 字，>80 字消息 → 括号被剥，对话保留
#   "他垂下眼睛，那种说不清楚的、像被什么轻轻压住的柔软" = 25 字 > 8 → strip
# ---------------------------------------------------------------------------
def test_case_b_long_paren_stripped_dialogue_kept():
    _paren_b = "（他垂下眼睛，那种说不清楚的、像被什么轻轻压住的柔软）"
    _tail_b = "嗯，我懂你的意思，今晚就好好睡吧，明天再说，别想那么多" * 3  # 81 chars
    input_b = _paren_b + _tail_b  # 27 + 81 = 108 > 80
    assert len(input_b) > 80
    result = _sanitize_assistant_message(input_b)
    assert _paren_b not in result
    assert "嗯，我懂你的意思" in result


# ---------------------------------------------------------------------------
# case C: 混合 — 短括号（"笑" = 1字）保留，长括号（20字）剥离
# ---------------------------------------------------------------------------
def test_case_c_mixed_short_kept_long_stripped():
    # 用 _PAD 确保 > 80，不依赖手工字数计算
    input_c = (
        "（笑）"                                           # inner "笑" = 1 ≤ 8 → keep
        "真的不是开玩笑啊"
        "（这种事情我真的从来没想过会发生在自己身上）"     # inner 20 > 8 → strip
        + _PAD
    )
    assert len(input_c) > 80
    result = _sanitize_assistant_message(input_c)
    assert "（笑）" in result
    assert "（这种事情我真的从来没想过会发生在自己身上）" not in result


# ---------------------------------------------------------------------------
# case D: 边界 — 括号内容正好 8 字 → 保留
#   "轻轻地摸了摸大白" = 8 字 ≤ 8 → keep
# ---------------------------------------------------------------------------
def test_case_d_boundary_8_chars_preserved():
    _paren_d = "（轻轻地摸了摸大白）"
    inner_d = _paren_d[1:-1]
    assert len(inner_d) == 8, f"前提：inner应为8字，实际{len(inner_d)}"
    input_d = _paren_d + _PAD  # 10 + 92 = 102 > 80
    assert len(input_d) > 80
    result = _sanitize_assistant_message(input_d)
    assert _paren_d in result


# ---------------------------------------------------------------------------
# case E: 边界 — 括号内容正好 9 字 → 剥离
#   "轻轻地摸了摸大白头" = 9 字 > 8 → strip
# ---------------------------------------------------------------------------
def test_case_e_boundary_9_chars_stripped():
    _paren_e = "（轻轻地摸了摸大白头）"
    inner_e = _paren_e[1:-1]
    assert len(inner_e) == 9, f"前提：inner应为9字，实际{len(inner_e)}"
    input_e = _paren_e + _PAD  # 11 + 92 = 103 > 80
    assert len(input_e) > 80
    result = _sanitize_assistant_message(input_e)
    assert _paren_e not in result


# ---------------------------------------------------------------------------
# case F: 短消息 ≤80 字 → 完全不进脱敏分支，长括号也保留
# ---------------------------------------------------------------------------
def test_case_f_short_message_long_paren_unchanged():
    input_f = "（这里其实有一段很长的心理描写但是消息整体很短）嗯"
    assert len(input_f) <= 80
    assert _sanitize_assistant_message(input_f) == input_f


# ---------------------------------------------------------------------------
# case G: 回归 — 原 case 1~5 的行为必须不变（通过引用各函数直接验证）
#   此处只做"标记性"断言，确保新代码没有破坏短消息/第三人称两条路径
# ---------------------------------------------------------------------------
def test_case_g_regression_short_message():
    # 对应原 case 2: 短消息原样返回
    short = "嗯，今天怎么样？吃饭了没"
    assert _sanitize_assistant_message(short) == short


def test_case_g_regression_third_person():
    # 对应原 case 1: 纯第三人称长文本返回 "..." 或大幅缩短
    input_tp = (
        "他收到你那个'好噢'时，在屏幕那头轻轻弯了一下嘴角"
        "——不是笑出声，是那种看到熟悉的语气词时，"
        "从眼底浮现出来的、被安稳到的柔软。"
        "他放下手里的书，给大白换水时顺便拍了一张照片发给你。"
    )
    assert len(input_tp) > 80
    result = _sanitize_assistant_message(input_tp)
    assert result == "..." or len(result) < len(input_tp) // 2
