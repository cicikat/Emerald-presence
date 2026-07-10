"""
tests/test_silent_failure.py — Brief 35 §3：静默失败可见化

Coverage:
1.  note() 计数 / last_error / last_ts 正确累加
2.  note() 自身绝不抛错（畸形输入也不外泄）
3.  snapshot() 返回独立拷贝，不污染内部状态
4.  GET /system/health 返回 started_at + silent_failures 结构
5.  挂点触发：mock 一个写失败（short_term.save）后计数 +1
"""

from __future__ import annotations

import pytest

from core import silent_failure


@pytest.fixture(autouse=True)
def _reset():
    silent_failure.reset_for_test()
    yield
    silent_failure.reset_for_test()


# ── 1 & 2. note() 计数正确 / 自身不抛错 ──────────────────────────────────────

def test_note_accumulates_count_and_last_error():
    silent_failure.note("mod_a", ValueError("boom1"))
    silent_failure.note("mod_a", ValueError("boom2"))

    snap = silent_failure.snapshot()
    assert snap["mod_a"]["count"] == 2
    assert "boom2" in snap["mod_a"]["last_error"]
    assert snap["mod_a"]["last_ts"] > 0


def test_note_never_raises_on_malformed_input():
    # err 不是 Exception，甚至 str() 本身可能抛错的对象
    class _Unstringable:
        def __str__(self):
            raise RuntimeError("can't stringify me")

    silent_failure.note("mod_b", _Unstringable())  # 不应抛出
    silent_failure.note(None, ValueError("x"))      # module 参数异常也不应抛出


# ── 3. snapshot() 独立拷贝 ───────────────────────────────────────────────────

def test_snapshot_is_independent_copy():
    silent_failure.note("mod_c", ValueError("boom"))
    snap = silent_failure.snapshot()
    snap["mod_c"]["count"] = 999
    snap["new_key"] = {"count": 1}

    fresh = silent_failure.snapshot()
    assert fresh["mod_c"]["count"] == 1
    assert "new_key" not in fresh


# ── 4. /system/health 返回结构 ───────────────────────────────────────────────

def test_system_health_endpoint_returns_expected_shape(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from admin.routers.system import router as system_router

    monkeypatch.setattr("admin.auth.get_admin_secret", lambda: "health-test-token")

    silent_failure.note("event_log.append", ValueError("disk full"))

    app = FastAPI()
    app.include_router(system_router)
    resp = TestClient(app).get(
        "/system/health",
        headers={"Authorization": "Bearer health-test-token"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert "started_at" in body and isinstance(body["started_at"], (int, float))
    assert "silent_failures" in body
    assert body["silent_failures"]["event_log.append"]["count"] == 1


def test_system_health_requires_auth():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from admin.routers.system import router as system_router

    app = FastAPI()
    app.include_router(system_router)
    resp = TestClient(app).get("/system/health")
    assert resp.status_code in (401, 403)


# ── 5. 挂点触发：short_term.save 写失败后计数 +1 ─────────────────────────────

def test_short_term_save_failure_is_noted(sandbox, monkeypatch):
    from core.memory import short_term

    def _boom(*a, **kw):
        raise OSError("disk write failed")

    monkeypatch.setattr("core.memory.short_term.safe_write_json", _boom)

    ok = short_term._save("u_silent_failure_test", [{"role": "user", "content": "hi"}])

    assert ok is False
    snap = silent_failure.snapshot()
    assert snap["short_term.save"]["count"] == 1
    assert "disk write failed" in snap["short_term.save"]["last_error"]
