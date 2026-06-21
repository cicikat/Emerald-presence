"""
Logging filter: redact sensitive query-param values from uvicorn access logs.

uvicorn access records carry args = (client_addr, method, full_path,
http_version, status_code).  full_path (index 2) may contain raw query
strings such as ?token=<secret>.  This filter replaces the values of
sensitive params with *** before the AccessFormatter formats the record.
"""

import logging
import re

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


def install_console_quiet_mode() -> None:
    """Suppress high-frequency INFO noise on the console.

    - uvicorn.access: 2xx/3xx entries dropped; 4xx/5xx still surface.
    - prompt_builder.debug: raised to WARNING (layer-size lines silenced).
      prompt_builder.token (trim/budget warnings) is unaffected.
    """
    install_access_noise_filter()
    logging.getLogger("prompt_builder.debug").setLevel(logging.WARNING)
