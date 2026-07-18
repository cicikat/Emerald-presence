"""
Logging filter: redact sensitive query-param values from uvicorn access logs.

uvicorn access records carry args = (client_addr, method, full_path,
http_version, status_code).  full_path (index 2) may contain raw query
strings such as ?token=<secret>.  This filter replaces the values of
sensitive params with *** before the AccessFormatter formats the record.
"""

import logging
import re
import time

_SENSITIVE = re.compile(r'(?i)((?:token|secret)=)[^&\s#]*')


class QuerySanitizeFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple) and len(record.args) >= 3:
            lst = list(record.args)
            lst[2] = _SENSITIVE.sub(r'\1***', str(lst[2]))
            record.args = tuple(lst)
        return True


def install_access_log_sanitizer() -> None:
    logging.getLogger("uvicorn.access").addFilter(QuerySanitizeFilter())


# Windows Proactor cleanup noise: when a remote peer resets an idle connection
# the OS raises WinError 10054 inside asyncio's _ProactorBasePipeTransport
# ._call_connection_lost().  This is expected behaviour on Windows and carries
# no signal — the connection is already gone.  Filter only this exact case so
# every other asyncio error continues to surface normally.
class _IgnoreWin10054ProactorFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if record.name != "asyncio":
            return True
        if "_ProactorBasePipeTransport._call_connection_lost" not in record.getMessage():
            return True
        exc = record.exc_info[1] if record.exc_info else None
        if isinstance(exc, ConnectionResetError) and getattr(exc, "winerror", None) == 10054:
            return False
        return True


def install_asyncio_proactor_noise_filter() -> None:
    logging.getLogger("asyncio").addFilter(_IgnoreWin10054ProactorFilter())


# ── Console quiet mode ────────────────────────────────────────────────────────
# uvicorn access log: args layout = (client_addr, method, full_path, http_version, status_code)
class DropSuccessfulAccessFilter(logging.Filter):
    """Drop 2xx/3xx uvicorn access entries; keep 4xx/5xx so errors surface."""
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple) and len(record.args) >= 5:
            try:
                if 200 <= int(record.args[4]) < 400:
                    return False
            except (ValueError, TypeError):
                pass
        return True


def install_access_noise_filter() -> None:
    lg = logging.getLogger("uvicorn.access")
    if any(isinstance(f, DropSuccessfulAccessFilter) for f in lg.filters):
        return
    lg.addFilter(DropSuccessfulAccessFilter())


# ── 401/429 重复告警降噪（Brief 97 §6）────────────────────────────────────────
# 桌面端指数退避（Emerald-client Brief 35）之前，同一来源短时间内反复鉴权失败/
# 被限流会让 uvicorn access 日志逐条刷屏。首条保留完整信息；同一 (来源, 状态码)
# 60s 窗口内的后续条目静默计数，窗口结束后下一条命中时改写成一行聚合摘要再放行
# ——不新增定时器，惰性地在下一次真实发生同类事件时才 flush。限流阈值本身
# （admin/auth.py 的 429 判定）不受影响，这里只处理日志噪音。
class SuppressRepeatedAuthFailureFilter(logging.Filter):
    """同一来源 IP 短时间内重复 401/429：首条完整，之后聚合为『N 次重复，已抑制』。"""

    _STATUSES = (401, 429)
    _WINDOW_SECONDS = 60

    def __init__(self, window_seconds: float = _WINDOW_SECONDS):
        super().__init__()
        self._window_seconds = window_seconds
        self._state: dict[tuple[str, int], dict] = {}

    def filter(self, record: logging.LogRecord) -> bool:
        if not (isinstance(record.args, tuple) and len(record.args) >= 5):
            return True
        try:
            status = int(record.args[4])
        except (ValueError, TypeError):
            return True
        if status not in self._STATUSES:
            return True

        client_addr = str(record.args[0])
        key = (client_addr, status)
        now = time.time()
        entry = self._state.get(key)

        if entry is None or now - entry["window_start"] > self._window_seconds:
            suppressed = entry["suppressed"] if entry else 0
            self._state[key] = {"window_start": now, "suppressed": 0}
            if suppressed > 0:
                record.msg = "%s - 上一窗口内状态 %s 重复，已抑制 %d 次"
                record.args = (client_addr, status, suppressed)
            return True

        entry["suppressed"] += 1
        return False


def install_auth_failure_dedup_filter() -> None:
    lg = logging.getLogger("uvicorn.access")
    if any(isinstance(f, SuppressRepeatedAuthFailureFilter) for f in lg.filters):
        return
    lg.addFilter(SuppressRepeatedAuthFailureFilter())


def install_console_quiet_mode() -> None:
    """Suppress high-frequency INFO noise on the console.

    - uvicorn.access: 2xx/3xx entries dropped; 4xx/5xx still surface.
    - prompt_builder.debug: raised to WARNING (layer-size lines silenced).
      prompt_builder.token (trim/budget warnings) is unaffected.
    """
    install_access_noise_filter()
    logging.getLogger("prompt_builder.debug").setLevel(logging.WARNING)
