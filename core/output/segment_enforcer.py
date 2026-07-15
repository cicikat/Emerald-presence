"""发送前段落兜底（Brief 72）。

这里只处理即将发送给用户的文本副本。调用方不得把结果写回 short_term，
否则会污染分段坍缩信号对模型原始输出的观测。
"""

from __future__ import annotations

import logging
import re

from core.config_loader import get_config
from core.memory.short_term import DEFAULT_SEGMENT_MIN_LEN

logger = logging.getLogger(__name__)

_SENTENCE_END_RE = re.compile(r"(?:[。！？]+|…+)")


def get_segment_enforce_settings() -> tuple[bool, int]:
    """返回运行时开关与有效阈值；读取异常时关闭兜底（fail-open）。"""
    try:
        config = get_config()
        output_config = config.get("output", {})
        segment_config = output_config.get("segment_enforce", {})
        anti_collapse_config = config.get("anti_collapse", {})
        min_len = segment_config.get(
            "min_len",
            anti_collapse_config.get("segment_min_len", DEFAULT_SEGMENT_MIN_LEN),
        )
        return bool(segment_config.get("enabled", False)), max(1, int(min_len))
    except Exception as exc:
        logger.warning("[segment_enforcer] 读取配置失败，跳过分段兜底: %s", exc)
        return False, DEFAULT_SEGMENT_MIN_LEN


def enforce_paragraph_breaks(text: str, *, min_len: int) -> str:
    """在长篇单段回复的合适句末插入一个段落空行。

    仅当文本尚无空行且长度超过 ``min_len`` 时处理。候选点限定为
    ``。！？…`` 句末，并选择最接近全文中点、左右均有正文的位置。
    函数只插入换行，不改写标点，也不增删字词；任何异常均返回原文。
    """
    original = text
    try:
        if not isinstance(text, str):
            return original
        threshold = max(1, int(min_len))
        if len(text) <= threshold or "\n\n" in text:
            return text

        candidates: list[int] = []
        for match in _SENTENCE_END_RE.finditer(text):
            index = match.end()
            if text[:index].strip() and text[index:].strip():
                candidates.append(index)
        if not candidates:
            return text

        midpoint = len(text) / 2
        split_at = min(candidates, key=lambda index: abs(index - midpoint))
        if text[split_at:split_at + 1] == "\n":
            return text[:split_at] + "\n" + text[split_at:]
        return text[:split_at] + "\n\n" + text[split_at:]
    except Exception as exc:
        logger.warning("[segment_enforcer] 分段兜底失败，返回原文: %s", exc)
        return original
