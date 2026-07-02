"""
pytest 共享 fixture

- sandbox：将 DataPaths._base 重定向到 tmp_path，隔离文件 I/O
- reset_slow_queue（autouse）：每个测试前重置 slow_queue 模块状态，测试后清理 worker
"""

import asyncio
import os
import sys
from pathlib import Path

import pytest

# 将 Emerald-presence 根目录设为工作目录，保证 config.yaml 等相对路径可被正确读取
_ROOT = Path(__file__).parent.parent
os.chdir(_ROOT)
sys.path.insert(0, str(_ROOT))


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """将 DataPaths._base 替换为 tmp_path，使文件读写不污染生产数据。"""
    import core.sandbox as _sandbox
    paths = _sandbox.DataPaths(mode="test", test_session_id="pytest_unit")
    paths._base = tmp_path
    monkeypatch.setattr(_sandbox, "_instance", paths)
    return paths


@pytest.fixture(autouse=True)
def reset_perceive_event_registry():
    """Reset perceive_event dedup registry before each test (prevents cross-test leakage)."""
    from core.perceive_event import clear_dedup_registry_for_test
    clear_dedup_registry_for_test()
    yield
    clear_dedup_registry_for_test()


@pytest.fixture(autouse=True)
def reset_proactive_ledger():
    """Reset ProactiveLedger module state before each test (CC 任务 19 · B).

    core/scheduler/proactive_ledger.py holds module-level next_allowed_ts /
    daily_count / recent state that persists across tests in the same process
    (mirrors loop._last_trigger, which individual tests already reset ad hoc).
    Without this, a test that calls execute_prompt()/record_send() successfully
    can leave next_allowed_ts in the future, causing an unrelated later test's
    gating._decide() to spuriously fail with global_gap_filtered.
    """
    from core.scheduler import proactive_ledger as _ledger
    _ledger._state = {
        "next_allowed_ts": 0.0,
        "daily_count": 0,
        "daily_logical_day": "",
        "recent": [],
    }
    _ledger._loaded = True  # skip disk load; state above is authoritative for the test
    yield


@pytest.fixture(autouse=True)
async def reset_slow_queue():
    """每个测试前重置 slow_queue 模块状态（队列/handler/worker），测试后清理 worker。"""
    import core.post_process.slow_queue as sq

    # 取消上一个测试遗留的 worker（若有）
    if sq._worker_task is not None and not sq._worker_task.done():
        sq._worker_task.cancel()
        try:
            await sq._worker_task
        except asyncio.CancelledError:
            pass

    # 用绑定当前 event loop 的新 Queue 替换旧实例，清空 handler 注册表
    sq._queue = asyncio.Queue()
    sq._handlers = {}
    sq._worker_task = None

    yield

    # 测试结束后清理 worker
    if sq._worker_task is not None and not sq._worker_task.done():
        sq._worker_task.cancel()
        try:
            await sq._worker_task
        except asyncio.CancelledError:
            pass
    sq._worker_task = None
