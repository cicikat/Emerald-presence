"""
tests/test_admin_user_facts_endpoint.py — Brief 89 §3: GET /{user_id}/facts 只读观测端点
"""
from __future__ import annotations

import pytest

UID_PREFIX = "gf_admin"
VALID_TOKEN = "gf-admin-test-secret"


@pytest.fixture
def admin_client(sandbox, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    monkeypatch.setattr("admin.auth.get_admin_secret", lambda: VALID_TOKEN)
    from admin.routers.users import router as users_router
    app = FastAPI()
    app.include_router(users_router)
    return TestClient(app)


def _auth():
    return {"Authorization": f"Bearer {VALID_TOKEN}"}


def test_admin_get_facts_returns_full_dict(sandbox, admin_client):
    from core.memory import user_facts as uf

    uid = f"{UID_PREFIX}_get"
    uf.save_user_facts(uid, {"timezone": "Asia/Shanghai", "device_os": "Windows"})

    resp = admin_client.get(f"/{uid}/facts", headers=_auth())

    assert resp.status_code == 200
    body = resp.json()
    assert body["user_id"] == uid
    assert body["facts"]["timezone"] == "Asia/Shanghai"
    assert body["facts"]["device_os"] == "Windows"


def test_admin_get_facts_empty_when_absent(sandbox, admin_client):
    resp = admin_client.get(f"/{UID_PREFIX}_absent/facts", headers=_auth())
    assert resp.status_code == 200
    assert resp.json()["facts"] == {}
