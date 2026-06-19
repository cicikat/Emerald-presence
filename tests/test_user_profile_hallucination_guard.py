"""
tests/test_user_profile_hallucination_guard.py — FIX-11

验收：
1. 角色脑补不入 profile：用户从未说过职业，角色说"你做设计的吧"，
   传给 LLM 的提取文本里不含 AI 发言内容。
2. 用户自陈正常入 profile：用户明确说"我是护士" → occupation 写入。
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest


_NULL_EXTRACTION = json.dumps({
    "name": None,
    "location": None,
    "pets": None,
    "interests": None,
    "occupation": None,
    "important_facts": [],
})

_NURSE_EXTRACTION = json.dumps({
    "name": None,
    "location": None,
    "pets": None,
    "interests": None,
    "occupation": "护士",
    "important_facts": [],
})


@pytest.mark.asyncio
async def test_ai_hallucination_not_in_extractor_input(sandbox):
    """角色发言不应出现在传给 LLM 的提取输入中"""
    captured: list[dict] = []

    async def fake_chat(messages, **kwargs):
        captured.extend(messages)
        return _NULL_EXTRACTION

    messages = [
        {"role": "user", "content": "哈哈"},
        {"role": "assistant", "content": "你做设计的对吧"},
        {"role": "user", "content": "嗯"},
    ]

    with patch("core.llm_client.chat", new=AsyncMock(side_effect=fake_chat)):
        from core.memory import user_profile
        await user_profile.extract_and_update("uid_halluc_test", messages)

    assert captured, "llm_client.chat 应被调用"
    user_msg = next((m["content"] for m in captured if m["role"] == "user"), "")
    assert "你做设计的对吧" not in user_msg, (
        "AI发言不应出现在传给提取 LLM 的 user 消息里"
    )


@pytest.mark.asyncio
async def test_ai_hallucination_occupation_not_written(sandbox):
    """角色脑补职业时，profile 的 occupation 应保持 null"""

    async def fake_chat(messages, **kwargs):
        # 模拟 LLM 只看到用户"哈哈"和"嗯"，无法提取职业
        return _NULL_EXTRACTION

    messages = [
        {"role": "user", "content": "哈哈"},
        {"role": "assistant", "content": "你做设计的对吧"},
        {"role": "user", "content": "嗯"},
    ]

    with patch("core.llm_client.chat", new=AsyncMock(side_effect=fake_chat)):
        from core.memory import user_profile
        await user_profile.extract_and_update("uid_occ_null", messages)

    profile = user_profile.load("uid_occ_null")
    assert profile["occupation"] is None


@pytest.mark.asyncio
async def test_user_self_report_written_to_profile(sandbox):
    """用户明确自陈职业时，profile 应正常写入"""

    async def fake_chat(messages, **kwargs):
        return _NURSE_EXTRACTION

    messages = [
        {"role": "user", "content": "我是护士，在医院上班"},
        {"role": "assistant", "content": "哇，护士辛苦了！"},
    ]

    with patch("core.llm_client.chat", new=AsyncMock(side_effect=fake_chat)):
        from core.memory import user_profile
        await user_profile.extract_and_update("uid_nurse", messages)

    profile = user_profile.load("uid_nurse")
    assert profile["occupation"] == "护士"
