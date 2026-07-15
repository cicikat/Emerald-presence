"""Brief 72：生成后段落硬兜底、双输出路径与热开关。"""

from pathlib import Path

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from admin.auth import TokenInfo
from admin.routers.settings_misc import router as settings_misc_router


def test_long_single_paragraph_gets_one_blank_line():
    from core.output.segment_enforcer import enforce_paragraph_breaks

    text = "第一句在这里慢慢铺开一些内容。第二句继续补充足够多的细节。第三句收束这段回复。"
    result = enforce_paragraph_breaks(text, min_len=20)

    assert "\n\n" in result
    assert result.replace("\n", "") == text


def test_short_reply_is_unchanged():
    from core.output.segment_enforcer import enforce_paragraph_breaks

    text = "嗯，我在。"
    assert enforce_paragraph_breaks(text, min_len=40) == text


def test_existing_paragraph_break_is_unchanged():
    from core.output.segment_enforcer import enforce_paragraph_breaks

    text = "第一段已经分好了。\n\n第二段不应再加工。"
    assert enforce_paragraph_breaks(text, min_len=5) == text


def test_no_sentence_boundary_is_unchanged():
    from core.output.segment_enforcer import enforce_paragraph_breaks

    text = "这是一段很长但完全没有目标句末标点的回复内容"
    assert enforce_paragraph_breaks(text, min_len=10) == text


def test_invalid_min_len_fails_open():
    from core.output.segment_enforcer import enforce_paragraph_breaks

    text = "第一句足够长。第二句也足够长。"
    assert enforce_paragraph_breaks(text, min_len="invalid") == text  # type: ignore[arg-type]


def test_effective_threshold_falls_back_to_s4(monkeypatch):
    import core.output.segment_enforcer as segment_enforcer

    monkeypatch.setattr(
        segment_enforcer,
        "get_config",
        lambda: {
            "anti_collapse": {"segment_min_len": 73},
            "output": {"segment_enforce": {"enabled": True}},
        },
    )
    assert segment_enforcer.get_segment_enforce_settings() == (True, 73)


@pytest.mark.parametrize("path", ["qq", "desktop"])
def test_enabled_setting_applies_to_both_output_paths(monkeypatch, path):
    import core.output.segment_enforcer as segment_enforcer

    monkeypatch.setattr(segment_enforcer, "get_segment_enforce_settings", lambda: (True, 20))
    text = "第一句在这里慢慢铺开一些内容。第二句继续补充足够多的细节。第三句收束这段回复。"

    if path == "qq":
        import core.response_processor as response_processor
        monkeypatch.setattr(response_processor, "get_segment_enforce_settings", lambda: (True, 20))
        result = "".join(response_processor.process(text, "Companion"))
    else:
        import core.reality_output_guard as reality_output_guard
        monkeypatch.setattr(reality_output_guard, "get_segment_enforce_settings", lambda: (True, 20))
        result = reality_output_guard.clean_reality_reply_text(text, "Companion")

    assert "\n\n" in result
    assert result.replace("\n", "") == text


def test_qq_memory_copy_preserves_original_paragraph_shape(monkeypatch):
    import core.response_processor as response_processor

    monkeypatch.setattr(response_processor, "get_segment_enforce_settings", lambda: (True, 20))
    text = "第一句在这里慢慢铺开一些内容。第二句继续补充足够多的细节。第三句收束这段回复。"

    visible = "".join(response_processor.process(text, "Companion"))
    memory = "".join(response_processor.process_memory_copy(text, "Companion"))

    assert "\n\n" in visible
    assert "\n\n" not in memory
    assert memory == text


def test_reality_memory_copy_preserves_original_paragraph_shape(monkeypatch):
    import core.reality_output_guard as reality_output_guard

    monkeypatch.setattr(reality_output_guard, "get_segment_enforce_settings", lambda: (True, 20))
    text = "第一句在这里慢慢铺开一些内容。第二句继续补充足够多的细节。第三句收束这段回复。"

    visible = reality_output_guard.clean_reality_reply_text(text, "Companion")
    memory = reality_output_guard.clean_reality_reply_text_for_memory(text, "Companion")

    assert "\n\n" in visible
    assert "\n\n" not in memory
    assert memory == text


@pytest.fixture
def persona_client():
    app = FastAPI()
    app.include_router(settings_misc_router)
    fake_persona = TokenInfo(label="test-desktop", scopes=frozenset({"persona"}))
    for route in settings_misc_router.routes:
        for dep in route.dependant.dependencies:
            if hasattr(dep.call, "_required_scopes"):
                app.dependency_overrides[dep.call] = lambda: fake_persona
    return TestClient(app)


def test_output_segment_enforce_api_hot_updates_config(
    tmp_path: Path,
    monkeypatch,
    persona_client,
):
    import admin.routers.settings_misc as settings_misc
    import core.config_loader as config_loader
    import core.output.segment_enforcer as segment_enforcer

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "anti_collapse": {"segment_min_len": 55},
                "output": {"segment_enforce": {"enabled": False}},
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings_misc, "CONFIG_FILE", config_path)
    monkeypatch.setattr(config_loader, "reload_config", lambda: None)
    monkeypatch.setattr(
        segment_enforcer,
        "get_config",
        lambda: yaml.safe_load(config_path.read_text(encoding="utf-8")),
    )

    initial = persona_client.get("/output-segment-enforce")
    assert initial.status_code == 200
    assert initial.json() == {"enabled": False, "min_len": 55}

    updated = persona_client.put(
        "/output-segment-enforce",
        json={"enabled": True, "min_len": 64},
    )
    assert updated.status_code == 200
    assert updated.json()["enabled"] is True
    assert updated.json()["min_len"] == 64
    saved = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert saved["output"]["segment_enforce"] == {"enabled": True, "min_len": 64}


def test_output_segment_enforce_api_rejects_invalid_threshold(persona_client):
    response = persona_client.put(
        "/output-segment-enforce",
        json={"enabled": True, "min_len": 0},
    )
    assert response.status_code == 422
