"""
detect_reply_length_collapse 单元测试（Brief 08 #1 字数反坍缩）
"""

from core.memory.short_term import detect_reply_length_collapse


def _history(lengths: list[int]) -> list[dict]:
    return [
        {"role": "assistant", "content": "字" * n}
        for n in lengths
    ]


def test_five_long_replies_trigger():
    # 五条都在 80-150 区间 -> 命中同一区间 -> 触发
    hint = detect_reply_length_collapse(_history([90, 95, 100, 110, 120]), recent_n=5)
    assert hint is not None
    assert "长" in hint or "短" in hint


def test_five_short_replies_trigger():
    # 五条都在 <15 区间 -> 触发
    hint = detect_reply_length_collapse(_history([3, 5, 8, 10, 12]), recent_n=5)
    assert hint is not None


def test_varied_lengths_not_triggered():
    # 长度本就有起伏，跨越多个区间 -> 不触发
    hint = detect_reply_length_collapse(_history([5, 60, 20, 200, 90]), recent_n=5)
    assert hint is None


def test_insufficient_history_not_triggered():
    # 不足 recent_n 条 -> 不触发（fail-open）
    hint = detect_reply_length_collapse(_history([90, 95]), recent_n=5)
    assert hint is None


def test_non_assistant_messages_ignored():
    history = [
        {"role": "user", "content": "字" * 100},
        {"role": "assistant", "content": "字" * 90},
        {"role": "assistant", "content": "字" * 95},
        {"role": "assistant", "content": "字" * 100},
        {"role": "assistant", "content": "字" * 110},
        {"role": "assistant", "content": "字" * 120},
    ]
    hint = detect_reply_length_collapse(history, recent_n=5)
    assert hint is not None


def test_custom_thresholds():
    # 自定义区间边界仍生效
    hint = detect_reply_length_collapse(
        _history([2, 3, 4, 4, 3]), recent_n=5, thresholds=(5, 10)
    )
    assert hint is not None
