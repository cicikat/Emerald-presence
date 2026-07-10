"""
Smoke test for core.scheduler.triggers.sensor_aware
Run from project root: python -X utf8 tests/manual/smoke_sensor_aware.py

场景 A — sensor_events.tick() 返回 []
          → handle_tick() 静默返回，_pipeline_send 不被调用

场景 B — tick 返回一个事件，judge 返回 tier=drop
          → _pipeline_send 不被调用

场景 C — tick 返回一个事件，judge 返回 tier=medium，全局冷却已过期
          → _pipeline_send 调用一次，prompt 含 "他想开口。"
          → mark_proactive_sent() 被调用

场景 D — tick 返回两个事件，judge 给出 score=40 和 75
          → 选 score=75 那个（whisper="他得说点什么了。"），40 那个不进 _pipeline_send
"""
import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

# 预先 import 被测模块（让 module cache 生效，patch 路径固定）
import core.scheduler.triggers.sensor_aware as sa


# ── 共用 fixture 数据 ─────────────────────────────────────────────────────────

_EVENT_MEDIUM = {
    "type": "LONG_FOCUS",
    "narrative": "她已经在 Code.exe 里连续工作了 26 分钟。",
    "context": {
        "local_hour": 15,
        "presence": "active",
        "focus_app": "Code.exe",
        "focus_title_hint": "ChatPanel.tsx",
        "continuous_at_desk_seconds": 5400,
        "minutes_since_last_chat": 70,
        "keystroke_density": "一般",
    },
}

_JUDGE_MEDIUM = {"score": 65, "reason": "适合开口", "intent_tier": "medium"}
_JUDGE_DROP   = {"score": 25, "reason": "无价值",   "intent_tier": "drop"}


def ok(cond: bool, label: str):
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}")


# ── 场景 A ────────────────────────────────────────────────────────────────────

async def scene_a():
    print("\n=== 场景 A: tick() 返回 [] → 静默返回，无副作用 ===")

    with (
        patch("core.scheduler.sensor_events.tick", return_value=[]),
        patch(
            "core.scheduler.triggers.sensor_aware._pipeline_send",
            new_callable=AsyncMock,
        ) as mock_send,
        patch("core.scheduler.sensor_events.mark_proactive_sent") as mock_mark,
    ):
        await sa.handle_tick()

    ok(mock_send.call_count == 0, "_pipeline_send 未被调用")
    ok(mock_mark.call_count == 0, "mark_proactive_sent 未被调用")


# ── 场景 B ────────────────────────────────────────────────────────────────────

async def scene_b():
    print("\n=== 场景 B: judge 返回 tier=drop → _pipeline_send 不调用 ===")

    with (
        patch("core.scheduler.sensor_events.tick", return_value=[_EVENT_MEDIUM]),
        patch(
            "core.scheduler.sensor_judge.judge",
            new_callable=AsyncMock,
            return_value=_JUDGE_DROP,
        ),
        patch(
            "core.scheduler.triggers.sensor_aware._pipeline_send",
            new_callable=AsyncMock,
        ) as mock_send,
        patch("core.scheduler.sensor_events.mark_proactive_sent") as mock_mark,
    ):
        await sa.handle_tick()

    ok(mock_send.call_count == 0, "_pipeline_send 未被调用")
    ok(mock_mark.call_count == 0, "mark_proactive_sent 未被调用")


# ── 场景 C ────────────────────────────────────────────────────────────────────

async def scene_c():
    print("\n=== 场景 C: tier=medium，冷却已过期 → 发送，prompt 含 '他想开口。' ===")

    with (
        patch("core.scheduler.sensor_events.tick", return_value=[_EVENT_MEDIUM]),
        patch(
            "core.scheduler.sensor_judge.judge",
            new_callable=AsyncMock,
            return_value=_JUDGE_MEDIUM,
        ),
        patch(
            "core.scheduler.sensor_events.get_last_proactive_at",
            return_value=None,  # 从未主动发过 → 冷却已过期
        ),
        patch(
            "core.scheduler.triggers.sensor_aware._pipeline_send",
            new_callable=AsyncMock,
        ) as mock_send,
        patch("core.scheduler.sensor_events.mark_proactive_sent") as mock_mark,
    ):
        await sa.handle_tick()

    ok(mock_send.call_count == 1, "_pipeline_send 被调用一次")
    if mock_send.call_count == 1:
        prompt = mock_send.call_args[0][0]
        ok("他想开口。" in prompt, f'prompt 含 "他想开口。" (实际: {prompt[:60]!r}...)')
        ok(mock_send.call_args.kwargs.get("trigger_name") == "sensor_aware",
           'trigger_name="sensor_aware"')
    ok(mock_mark.call_count == 1, "mark_proactive_sent 被调用一次")


# ── 场景 D ────────────────────────────────────────────────────────────────────

async def scene_d():
    print("\n=== 场景 D: 两个事件 score=40/75 → 选 75，whisper='他得说点什么了。' ===")

    event_low = {
        "type": "FOCUS_SCATTERED",
        "narrative": "她在 5 分钟内切换了 20 次窗口。",
        "context": {
            "local_hour": 14,
            "presence": "active",
            "focus_app": "chrome.exe",
            "focus_title_hint": "",
            "continuous_at_desk_seconds": 3700,
            "minutes_since_last_chat": 40,
            "keystroke_density": "稀疏",
        },
    }
    event_high = {
        "type": "LATE_NIGHT_ACTIVE",
        "narrative": "已经凌晨 2 点了，她还醒着。",
        "context": {
            "local_hour": 2,
            "presence": "active",
            "focus_app": "chrome.exe",
            "focus_title_hint": "",
            "continuous_at_desk_seconds": 7500,
            "minutes_since_last_chat": 8,
            "keystroke_density": "一般",
        },
    }

    judge_table = {
        "FOCUS_SCATTERED":   {"score": 40, "reason": "普通", "intent_tier": "drop"},
        "LATE_NIGHT_ACTIVE": {"score": 75, "reason": "深夜活跃", "intent_tier": "strong"},
    }

    async def fake_judge(ev):
        return judge_table[ev["type"]]

    with (
        patch(
            "core.scheduler.sensor_events.tick",
            return_value=[event_low, event_high],
        ),
        patch("core.scheduler.sensor_judge.judge", side_effect=fake_judge),
        patch(
            "core.scheduler.sensor_events.get_last_proactive_at",
            return_value=None,
        ),
        patch(
            "core.scheduler.triggers.sensor_aware._pipeline_send",
            new_callable=AsyncMock,
        ) as mock_send,
        patch("core.scheduler.sensor_events.mark_proactive_sent"),
    ):
        await sa.handle_tick()

    ok(mock_send.call_count == 1, "_pipeline_send 被调用一次（不是两次）")
    if mock_send.call_count == 1:
        prompt = mock_send.call_args[0][0]
        ok("他得说点什么了。" in prompt,
           f'prompt 含 "他得说点什么了。"（实际: {prompt[:60]!r}...）')
        ok("他想开口。" not in prompt,
           'prompt 不含低分事件的 whisper')


# ── 入口 ──────────────────────────────────────────────────────────────────────

async def main():
    await scene_a()
    await scene_b()
    await scene_c()
    await scene_d()
    print("\n=== Smoke 完成 ===\n")


if __name__ == "__main__":
    asyncio.run(main())
