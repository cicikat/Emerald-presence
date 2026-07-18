"""
tests/test_secrets_book.py — Brief 93 §2：管理面板「打开密钥本」快捷入口

GET  /system/secrets-book       — 仅本机请求可用（悬浮按钮显隐依据）
POST /system/secrets-book/open  — 用系统默认程序打开 secrets.local.yaml；非本机 403
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from admin.auth import TokenInfo
from admin.routers.system import router as system_router


@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(system_router)
    fake_admin = TokenInfo(label="test-admin", scopes=frozenset({"admin"}))
    for route in system_router.routes:
        for dep in route.dependant.dependencies:
            if hasattr(dep.call, "_required_scopes"):
                app.dependency_overrides[dep.call] = lambda: fake_admin
    return app


def _local_client(app):
    return TestClient(app, client=("127.0.0.1", 51000))


def _remote_client(app):
    return TestClient(app, client=("203.0.113.5", 51000))


def test_status_reports_available_for_localhost(app, tmp_path, monkeypatch):
    import admin.routers.system as sysmod
    monkeypatch.setattr(sysmod, "_SECRETS_LOCAL_PATH", tmp_path / "secrets.local.yaml")
    resp = _local_client(app).get("/system/secrets-book")
    assert resp.status_code == 200
    assert resp.json()["available"] is True


def test_status_reports_unavailable_for_remote(app, tmp_path, monkeypatch):
    import admin.routers.system as sysmod
    monkeypatch.setattr(sysmod, "_SECRETS_LOCAL_PATH", tmp_path / "secrets.local.yaml")
    resp = _remote_client(app).get("/system/secrets-book")
    assert resp.status_code == 200
    assert resp.json()["available"] is False


def test_open_rejects_remote_request(app, tmp_path, monkeypatch):
    import admin.routers.system as sysmod
    secrets_path = tmp_path / "secrets.local.yaml"
    secrets_path.write_text("tokens: {}\n", encoding="utf-8")
    monkeypatch.setattr(sysmod, "_SECRETS_LOCAL_PATH", secrets_path)
    resp = _remote_client(app).post("/system/secrets-book/open")
    assert resp.status_code == 403


def test_open_returns_404_when_file_missing(app, tmp_path, monkeypatch):
    import admin.routers.system as sysmod
    monkeypatch.setattr(sysmod, "_SECRETS_LOCAL_PATH", tmp_path / "does-not-exist.yaml")
    resp = _local_client(app).post("/system/secrets-book/open")
    assert resp.status_code == 404


def test_open_invokes_os_startfile_on_local_request(app, tmp_path, monkeypatch):
    import sys
    import admin.routers.system as sysmod
    secrets_path = tmp_path / "secrets.local.yaml"
    secrets_path.write_text("tokens: {}\n", encoding="utf-8")
    monkeypatch.setattr(sysmod, "_SECRETS_LOCAL_PATH", secrets_path)

    calls = []
    if sys.platform == "win32":
        monkeypatch.setattr(sysmod.os, "startfile", lambda p: calls.append(p), raising=False)
    else:
        import subprocess
        monkeypatch.setattr(subprocess, "Popen", lambda args: calls.append(args))

    resp = _local_client(app).post("/system/secrets-book/open")
    assert resp.status_code == 200
    assert calls
