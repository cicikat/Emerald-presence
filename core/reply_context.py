"""
reply_context — 引用回复(reply_to)前缀构造（Brief 98 §2）。

desktop / mobile 共用契约：聊天请求体可选携带
    reply_to: {text: str, ts: float}
表示用户正在回复角色某条历史气泡。v0.1 不建消息 ID 体系，只用文本+时间戳。

前缀直接拼进用户消息内容，随 message 一起进入 pipeline（fetch_context /
build_prompt / capture_turn），short_term / mid_term / event_log 因此自然捕获，
无需任何记忆层改造。

校验失败（text 为空、ts 非法）一律静默降级为普通消息，不抛异常——引用回复是
体验增强，不应该因为客户端传参异常而打断整轮对话。
"""

from __future__ import annotations

import time
from datetime import datetime

_MAX_TEXT_LEN = 200
# 允许的未来时间容差：抵消客户端/服务端小幅时钟偏差，不代表真的接受"未来消息"。
_FUTURE_TOLERANCE_SEC = 5.0


def format_relative_time(ts: float, now: float | None = None) -> str:
    """把时间戳格式化为「今天 HH:MM」/「N 天前」/「M月D日」。

    按自然日边界判定（非按 24h 滚动窗口）：
    - 与 now 同一天 → 今天 HH:MM
    - 相差 1-6 个自然日 → N 天前
    - 相差 >=7 个自然日 → M月D日
    """
    if now is None:
        now = time.time()
    dt = datetime.fromtimestamp(ts)
    now_dt = datetime.fromtimestamp(now)
    delta_days = (now_dt.date() - dt.date()).days
    if delta_days <= 0:
        return f"今天 {dt.strftime('%H:%M')}"
    if delta_days <= 6:
        return f"{delta_days}天前"
    return f"{dt.month}月{dt.day}日"


def build_reply_prefix(reply_to: dict | None, now: float | None = None) -> str | None:
    """校验 reply_to 并构造前缀；非法输入返回 None（调用方应降级为普通消息）。"""
    if not isinstance(reply_to, dict):
        return None
    text = reply_to.get("text")
    ts = reply_to.get("ts")
    if not isinstance(text, str) or not text.strip():
        return None
    if isinstance(ts, bool) or not isinstance(ts, (int, float)):
        return None
    ts = float(ts)
    if now is None:
        now = time.time()
    if ts < 0 or ts > now + _FUTURE_TOLERANCE_SEC:
        return None

    truncated = text.strip()[:_MAX_TEXT_LEN]
    rel = format_relative_time(ts, now)
    return f"用户回复了你{rel}发送的这条消息「{truncated}」："


def apply_reply_prefix(message: str, reply_to: dict | None, now: float | None = None) -> str:
    """在 message 前拼 reply_to 前缀；reply_to 缺失/非法时原样返回 message。"""
    prefix = build_reply_prefix(reply_to, now)
    return (prefix + message) if prefix else message
