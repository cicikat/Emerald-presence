"""Tests for admin.log_filter noise-suppression filters."""

import logging
import sys

import pytest

from admin.log_filter import (
    DropSuccessfulAccessFilter,
    _IgnoreWin10054ProactorFilter,
    install_access_noise_filter,
    install_asyncio_proactor_noise_filter,
    install_console_quiet_mode,
)

_MSG = "Exception in callback _ProactorBasePipeTransport._call_connection_lost()"


def _make_record(name: str, msg: str, exc: BaseException | None = None) -> logging.LogRecord:
    record = logging.LogRecord(
        name=name,
        level=logging.ERROR,
        pathname="",
        lineno=0,
        msg=msg,
        args=(),
        exc_info=(type(exc), exc, None) if exc else None,
    )
    return record


def _win10054() -> ConnectionResetError:
    err = ConnectionResetError("[WinError 10054] 远程主机强迫关闭了一个现有的连接。")
    err.winerror = 10054
    return err


# ── filter=False means suppressed ────────────────────────────────────────────

def test_suppresses_exact_winerror_10054():
    f = _IgnoreWin10054ProactorFilter()
    record = _make_record("asyncio", _MSG, _win10054())
    assert f.filter(record) is False


# ── filter=True means passes through ─────────────────────────────────────────

def test_passes_asyncio_error_without_exc_info():
    f = _IgnoreWin10054ProactorFilter()
    record = _make_record("asyncio", _MSG, exc=None)
    assert f.filter(record) is True


def test_passes_asyncio_connection_reset_without_winerror():
    f = _IgnoreWin10054ProactorFilter()
    err = ConnectionResetError("plain reset, no winerror attribute")
    record = _make_record("asyncio", _MSG, err)
    assert f.filter(record) is True


def test_passes_asyncio_connection_reset_wrong_winerror():
    f = _IgnoreWin10054ProactorFilter()
    err = ConnectionResetError()
    err.winerror = 10053  # WSAECONNABORTED — different code
    record = _make_record("asyncio", _MSG, err)
    assert f.filter(record) is True


def test_passes_asyncio_other_exception_type():
    f = _IgnoreWin10054ProactorFilter()
    err = OSError("unrelated os error")
    record = _make_record("asyncio", _MSG, err)
    assert f.filter(record) is True


def test_passes_asyncio_different_message():
    f = _IgnoreWin10054ProactorFilter()
    record = _make_record("asyncio", "some other asyncio error", _win10054())
    assert f.filter(record) is True


def test_passes_non_asyncio_logger():
    f = _IgnoreWin10054ProactorFilter()
    record = _make_record("uvicorn", _MSG, _win10054())
    assert f.filter(record) is True


def test_passes_root_logger():
    f = _IgnoreWin10054ProactorFilter()
    record = _make_record("root", _MSG, _win10054())
    assert f.filter(record) is True


def test_install_attaches_filter_to_asyncio_logger():
    asyncio_logger = logging.getLogger("asyncio")
    before = len(asyncio_logger.filters)
    install_asyncio_proactor_noise_filter()
    assert len(asyncio_logger.filters) == before + 1
    # cleanup so repeated test runs don't stack filters
    asyncio_logger.filters.pop()


# ── DropSuccessfulAccessFilter ────────────────────────────────────────────────

def _access_record(status_code: int) -> logging.LogRecord:
    record = logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg='%s - "%s %s HTTP/%s" %d',
        args=("127.0.0.1:12345", "GET", "/lorebook", "1.1", status_code),
        exc_info=None,
    )
    return record


@pytest.mark.parametrize("code", [200, 204, 301, 302, 304, 399])
def test_drop_successful_access_suppresses_2xx_3xx(code):
    f = DropSuccessfulAccessFilter()
    assert f.filter(_access_record(code)) is False


@pytest.mark.parametrize("code", [400, 401, 403, 404, 500, 502, 503])
def test_drop_successful_access_passes_4xx_5xx(code):
    f = DropSuccessfulAccessFilter()
    assert f.filter(_access_record(code)) is True


def test_drop_successful_access_passes_short_args():
    f = DropSuccessfulAccessFilter()
    record = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, "msg", ("only", "3"), None)
    assert f.filter(record) is True


def test_drop_successful_access_passes_non_tuple_args():
    f = DropSuccessfulAccessFilter()
    record = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, "msg", None, None)
    assert f.filter(record) is True


def test_install_access_noise_filter_attaches():
    lg = logging.getLogger("uvicorn.access")
    before_count = sum(1 for f in lg.filters if isinstance(f, DropSuccessfulAccessFilter))
    install_access_noise_filter()
    after_count = sum(1 for f in lg.filters if isinstance(f, DropSuccessfulAccessFilter))
    assert after_count == before_count + 1
    lg.filters = [f for f in lg.filters if not isinstance(f, DropSuccessfulAccessFilter)]


def test_install_access_noise_filter_idempotent():
    lg = logging.getLogger("uvicorn.access")
    lg.filters = [f for f in lg.filters if not isinstance(f, DropSuccessfulAccessFilter)]
    install_access_noise_filter()
    install_access_noise_filter()
    count = sum(1 for f in lg.filters if isinstance(f, DropSuccessfulAccessFilter))
    assert count == 1
    lg.filters = [f for f in lg.filters if not isinstance(f, DropSuccessfulAccessFilter)]


# ── install_console_quiet_mode ────────────────────────────────────────────────

def test_install_console_quiet_mode_sets_debug_logger_level():
    debug_lg = logging.getLogger("prompt_builder.debug")
    original = debug_lg.level
    install_console_quiet_mode()
    assert debug_lg.level == logging.WARNING
    debug_lg.setLevel(original)
    # cleanup access filter
    lg = logging.getLogger("uvicorn.access")
    lg.filters = [f for f in lg.filters if not isinstance(f, DropSuccessfulAccessFilter)]


def test_install_console_quiet_mode_attaches_access_filter():
    lg = logging.getLogger("uvicorn.access")
    lg.filters = [f for f in lg.filters if not isinstance(f, DropSuccessfulAccessFilter)]
    install_console_quiet_mode()
    assert any(isinstance(f, DropSuccessfulAccessFilter) for f in lg.filters)
    lg.filters = [f for f in lg.filters if not isinstance(f, DropSuccessfulAccessFilter)]


def test_install_console_quiet_mode_does_not_affect_token_logger():
    token_lg = logging.getLogger("prompt_builder.token")
    original = token_lg.level
    install_console_quiet_mode()
    assert token_lg.level == original
    # cleanup
    lg = logging.getLogger("uvicorn.access")
    lg.filters = [f for f in lg.filters if not isinstance(f, DropSuccessfulAccessFilter)]
