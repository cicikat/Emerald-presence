"""
Tests for detect_emotion() validation logic.

Covers:
- thinking / sleepy pass through (not fallen back to neutral)
- unrecognised emotion still falls back to neutral

Patching strategy (post multi-model preset refactor):
  detect_emotion now resolves a ModelClient via core.model_registry.get_model_client.
  We monkeypatch model_registry.get_model_client to inject a fake ModelClient
  instead of patching the internal _get_client shim.
"""

import types

import pytest

from core.model_registry import ModelClient


def _make_fake_model_client(emotion: str) -> ModelClient:
    """Return a minimal fake ModelClient whose client.chat.completions.create returns `emotion`."""

    async def fake_create(**kwargs):
        msg = types.SimpleNamespace(content=emotion)
        choice = types.SimpleNamespace(message=msg)
        return types.SimpleNamespace(choices=[choice])

    completions = types.SimpleNamespace(create=fake_create)
    chat_obj = types.SimpleNamespace(completions=completions)
    fake_client = types.SimpleNamespace(chat=chat_obj)

    return ModelClient(
        name="test",
        provider_kind="deepseek",
        model="test-model",
        tool_call_mode="function_calling",
        prompt_style="narrative",
        params={"temperature": 0.0, "max_tokens": 10},
        client=fake_client,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("emotion", ["thinking", "sleepy"])
async def test_new_emotions_not_fallen_back(emotion, monkeypatch):
    from core import llm_client

    # Patch the imported name inside llm_client (not the registry module attribute)
    monkeypatch.setattr(llm_client, "get_model_client", lambda cat: _make_fake_model_client(emotion))
    assert await llm_client.detect_emotion("some text") == emotion


@pytest.mark.asyncio
async def test_invalid_emotion_falls_back_to_neutral(monkeypatch):
    from core import llm_client

    monkeypatch.setattr(llm_client, "get_model_client", lambda cat: _make_fake_model_client("confused"))
    assert await llm_client.detect_emotion("some text") == "neutral"
