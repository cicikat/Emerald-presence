"""
SEC-AUTH-2 §7：鉴权审计日志。

data/runtime/auth/audit.jsonl 追加写入；写失败 fail-open（safe_append_jsonl 内部已
try/except，绝不向上抛出，不阻塞请求）。绝不记录 token 明文或 hash。
"""

import time

from core.safe_write import safe_append_jsonl
from core.sandbox import get_paths


def log_event(event: str, *, label: str | None = None, path: str | None = None, ip: str | None = None) -> None:
    record = {
        "ts": time.time(),
        "event": event,
        "label": label or "invalid",
        "path": path,
        "ip": ip,
    }
    safe_append_jsonl(get_paths().auth_audit_log(), record)
