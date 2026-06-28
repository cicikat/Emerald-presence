"""
tests/test_recall_gate.py — P0.5-2 recall_gate 单测

断言覆盖：
- backchannel 词 → True
- 单字符重复 → True
- 纯标点/空白/emoji → True
- 空串 → True
- 含实词的句子 → False
- 边界：方言/新词非命中 → False
"""

import pytest
from core.recall_gate import is_low_information


class TestLowInformationPositives:
    """应该被判为低信息（True）的输入"""

    @pytest.mark.parametrize("text", [
        "嗯",
        "嗯嗯",
        "嗯嗯嗯",
        "嗯哼",
        "唔",
        "哦",
        "噢",
        "哦哦",
        "好",
        "好的",
        "好吧",
        "好滴",
        "行",
        "成",
        "ok",
        "okk",
        "okok",
        "在",
        "在的",
        "哈",
        "哈哈",
        "哈哈哈",
        "嘿",
        "诶",
        "唉",
        "咪",
        "喵",
        "知道了",
        "晓得了",
        "收到",
        "懂了",
        "嗯呐",
    ])
    def test_backchannel_word(self, text):
        assert is_low_information(text) is True

    @pytest.mark.parametrize("text", [
        "喵喵喵",
        "哈哈哈哈哈",
        "嗯嗯嗯嗯",
        "唔唔唔",
        "啊啊啊",
    ])
    def test_single_char_repeat(self, text):
        assert is_low_information(text) is True

    @pytest.mark.parametrize("text", [
        "",
        "   ",
        "，。！？",
        "...",
        "😊",
        "😊😊😊",
        "，",
        "  ，  ",
    ])
    def test_empty_or_punctuation_or_emoji(self, text):
        assert is_low_information(text) is True

    def test_backchannel_with_surrounding_whitespace(self):
        assert is_low_information("  嗯嗯  ") is True

    def test_backchannel_with_punctuation(self):
        assert is_low_information("嗯。") is True

    def test_backchannel_ok_with_punctuation(self):
        assert is_low_information("ok！") is True


class TestLowInformationNegatives:
    """应该被判为非低信息（False）的输入"""

    @pytest.mark.parametrize("text", [
        "好的我去睡了",
        "今天好累啊",
        "喵星人",
        "哈哈哈哈但是真的好笑",
        "嗯，那我先回去了",
        "在吗？我有事",
        "知道了，下次注意",
        "我想你",
        "你好",
        "晚安",
        "谢谢",
    ])
    def test_real_content(self, text):
        assert is_low_information(text) is False

    def test_mixed_repeat_and_real_word(self):
        assert is_low_information("喵喵喵星人") is False

    def test_two_different_backchannel_chars_is_not_repeat(self):
        # "哈喵" 不在名单里，且两个不同字符，不是单字符重复
        assert is_low_information("哈喵") is False
