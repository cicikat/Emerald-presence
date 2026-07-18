import asyncio

import yaml

from admin.routers import settings_feature_flags as mod


def test_feature_flags_update_is_allowlisted(tmp_path, monkeypatch):
    path = tmp_path / "config.yaml"
    path.write_text("practice:\n  enabled: false\n", encoding="utf-8")
    monkeypatch.setattr(mod, "CONFIG_FILE", path)
    monkeypatch.setattr(mod, "get_config", lambda: yaml.safe_load(path.read_text(encoding="utf-8")))
    from core import config_loader
    monkeypatch.setattr(config_loader, "reload_config", lambda: None)

    result = asyncio.run(mod.update_feature_flags(mod.FeatureFlagsUpdate(flags={"practice": True}), auth=None))
    assert result["flags"]["practice"]["enabled"] is True
    assert yaml.safe_load(path.read_text(encoding="utf-8"))["practice"]["enabled"] is True


def test_feature_flags_reject_unknown(monkeypatch):
    import pytest
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        asyncio.run(mod.update_feature_flags(mod.FeatureFlagsUpdate(flags={"api_key": True}), auth=None))
    assert exc.value.status_code == 422


def test_qq_and_mail_channel_toggles_are_allowlisted(tmp_path, monkeypatch):
    """Brief 93 §4：auth-tokens 页「通道开关」区复用本白名单读写 qq.enabled / mail.enabled。"""
    path = tmp_path / "config.yaml"
    path.write_text("qq:\n  enabled: false\nmail:\n  enabled: false\n", encoding="utf-8")
    monkeypatch.setattr(mod, "CONFIG_FILE", path)
    monkeypatch.setattr(mod, "get_config", lambda: yaml.safe_load(path.read_text(encoding="utf-8")))
    from core import config_loader
    monkeypatch.setattr(config_loader, "reload_config", lambda: None)

    result = asyncio.run(
        mod.update_feature_flags(mod.FeatureFlagsUpdate(flags={"qq": True, "mail": True}), auth=None)
    )
    assert result["flags"]["qq"]["enabled"] is True
    assert result["flags"]["mail"]["enabled"] is True
    cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert cfg["qq"]["enabled"] is True
    assert cfg["mail"]["enabled"] is True
