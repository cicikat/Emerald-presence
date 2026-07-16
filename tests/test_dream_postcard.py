"""Dream postcard generation and delivery contracts."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


def _turns(count: int = 5) -> list[dict]:
    return [{"role": "assistant", "content": f"turn {i}", "ts": 1_700_000_000} for i in range(count)]


@pytest.mark.asyncio
async def test_postcard_system_prompt_contains_invariant_hint():
    from core.dream import postcard

    chat = AsyncMock(return_value="letter")
    invariant = {"situation": "你退缩时", "response": "先停下来等你"}
    with (
        patch.object(postcard, "_load_schedule", return_value=[]),
        patch.object(postcard, "_archive_turns", return_value=_turns()),
        patch.object(postcard, "_save_schedule", return_value=True),
        patch.object(postcard, "_template_text", return_value="template"),
        patch("core.dream.invariants.select_for_postcard", return_value=invariant),
        patch("core.llm_client.chat", chat),
    ):
        await postcard.generate_postcard("u", "d", "soft_exit")

    system = chat.await_args.args[0][0]["content"]
    assert "你退缩时" in system
    assert "先停下来等你" in system


@pytest.mark.asyncio
async def test_postcard_system_prompt_omits_invariant_hint_when_none():
    from core.dream import postcard

    chat = AsyncMock(return_value="letter")
    with (
        patch.object(postcard, "_load_schedule", return_value=[]),
        patch.object(postcard, "_archive_turns", return_value=_turns()),
        patch.object(postcard, "_save_schedule", return_value=True),
        patch.object(postcard, "_template_text", return_value="template"),
        patch("core.dream.invariants.select_for_postcard", return_value=None),
        patch("core.llm_client.chat", chat),
    ):
        await postcard.generate_postcard("u", "d", "soft_exit")

    system = chat.await_args.args[0][0]["content"]
    assert "跨梦观察" not in system
