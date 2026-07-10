"""
静默失败可见化（Brief 35 §3）。

不改任何一处现有 except 的行为——原 log_error / logger 调用照旧，这里只在旁边
多记一笔进程内计数，供 GET /system/health 读出。审计结论：fail-open 是产品选择
（"不打扰她"），但失败要可见，静默不等于失明。

零依赖、自身绝不抛错：调用方本就站在 except 分支里，这里再出错也只能吞掉。
"""

import time

_PROCESS_STARTED_AT: float = time.time()

_counts: dict[str, dict] = {}


def note(module: str, err) -> None:
    """记一次静默失败。err 可以是 Exception 或任意可 str() 的对象。"""
    try:
        entry = _counts.setdefault(module, {"count": 0, "last_error": "", "last_ts": 0.0})
        entry["count"] += 1
        entry["last_error"] = str(err)[:300]
        entry["last_ts"] = time.time()
    except Exception:
        pass


def snapshot() -> dict[str, dict]:
    """返回计数表的浅拷贝，供 /system/health 读取。"""
    try:
        return {k: dict(v) for k, v in _counts.items()}
    except Exception:
        return {}


def process_started_at() -> float:
    return _PROCESS_STARTED_AT


def reset_for_test() -> None:
    """测试专用：清空计数表。"""
    _counts.clear()
