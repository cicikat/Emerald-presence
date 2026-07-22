"""表情包总开关与触发概率的 admin 配置接口。"""

from unittest.mock import patch

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient


VALID_TOKEN = "sticker-config-test-secret"


@pytest.fixture
def admin_client(tmp_path, monkeypatch):
    import admin.routers.settings_misc as settings_misc

    config_path = tmp_path / "config.yaml"
    monkeypatch.setattr(settings_misc, "CONFIG_FILE", config_path)
    monkeypatch.setattr(settings_misc, "get_config", lambda: yaml.safe_load(config_path.read_text(encoding="utf-8")) or {})
    monkeypatch.setattr("admin.auth.get_admin_secret", lambda: VALID_TOKEN)
    with patch("core.config_loader.reload_config", return_value=None):
        app = FastAPI()
        app.include_router(settings_misc.router)
        yield TestClient(app), config_path


def _auth():
    return {"Authorization": f"Bearer {VALID_TOKEN}"}


def test_sticker_config_defaults_preserve_legacy_behavior(admin_client):
    client, config_path = admin_client
    config_path.write_text("other: value\n", encoding="utf-8")

    response = client.get("/sticker-config", headers=_auth())

    assert response.status_code == 200
    assert response.json() == {"enabled": True, "trigger_prob": 0.06}


def test_sticker_config_update_persists_and_hot_reloads(admin_client):
    client, config_path = admin_client
    config_path.write_text("sticker:\n  enabled: true\n  trigger_prob: 0.06\n", encoding="utf-8")

    response = client.put(
        "/sticker-config",
        json={"enabled": False, "trigger_prob": 0.4},
        headers=_auth(),
    )

    assert response.status_code == 200
    assert response.json()["enabled"] is False
    assert response.json()["trigger_prob"] == 0.4
    assert yaml.safe_load(config_path.read_text(encoding="utf-8"))["sticker"] == {
        "enabled": False,
        "trigger_prob": 0.4,
    }


@pytest.mark.parametrize("trigger_prob", [-0.01, 1.01])
def test_sticker_config_rejects_out_of_range_probability(admin_client, trigger_prob):
    client, config_path = admin_client
    config_path.write_text("sticker: {}\n", encoding="utf-8")

    response = client.put("/sticker-config", json={"trigger_prob": trigger_prob}, headers=_auth())

    assert response.status_code == 422


def test_sticker_config_requires_admin_scope(admin_client):
    client, config_path = admin_client
    config_path.write_text("sticker: {}\n", encoding="utf-8")

    assert client.get("/sticker-config").status_code == 401
