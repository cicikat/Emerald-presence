"""
sensor_aware_audit.py — sensor_aware 链路事后审计 ring buffer。

纯内存，重启清零，不持久化。
一次 handle_tick 调用对应 ring buffer 里的一条 snapshot。
"""
import logging
from collections import deque

logger = logging.getLogger(__name__)

_audit_log: deque[dict] = deque(maxlen=50)


def record(snapshot: dict) -> None:
    _audit_log.append(snapshot)


def get_recent(n: int = 50) -> list[dict]:
    """返回最近 n 条快照（新→旧）。n 上限 50。"""
    n = min(max(n, 1), 50)
    items = list(_audit_log)
    items.reverse()
    return items[:n]
