"""
Smoke test for core.scheduler.sensor_judge
Run from project root: python -X utf8 tests/manual/smoke_sensor_judge.py

场景 A — LONG_FOCUS，40 分钟未聊天，预期 score 偏中高、不 drop
场景 B — 同上，但 3 分钟前刚主动发过，预期 score <40 / drop
场景 C — LATE_NIGHT_ACTIVE 凌晨 2 点，预期 score 60-85
场景 D — PRESENCE_RETURNED 离开 8 分钟，预期 score 40-70
场景 E — LLM mock 返回非 JSON，预期兜底 drop 不抛异常
"""
import asyncio
import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import core.scheduler.sensor_judge as sj


# ── 工具函数 ─────────────────────────────────────────────────────────────────

def _event(type_: str, narrative: str, **ctx_overrides) -> dict:
    ctx = {
        "minutes_since_last_proactive": 50,
        "minutes_since_last_chat":      40,
        "local_hour":                   14,
        "presence":                     "active",
        "focus_app":                    "Code.exe",
        "focus_title_hint":             "ChatPanel.tsx",
        "continuous_at_desk_seconds":   5400,
        "keystroke_density":            "密集",
        "ye_xuan_activity":             "在写代码",
        **ctx_overrides,
    }
    return {"type": type_, "narrative": narrative, "context": ctx}


def show(label: str, r: dict):
    print(f"  event   : {label}")
    print(f"  score   : {r['score']}")
    print(f"  reason  : {r['reason']}")
    print(f"  tier    : {r['intent_tier']}")


def ok(cond: bool, label: str):
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}")


# ── 场景定义 ─────────────────────────────────────────────────────────────────

_LONG_FOCUS_BASE = _event(
    "LONG_FOCUS",
    "她已经在 Code.exe 里连续工作了 26 分钟。",
)


async def main():
    # ── 场景 A ────────────────────────────────────────────────────────────────
    print("\n=== 场景 A: LONG_FOCUS，40 分钟未聊天 ===")
    ra = await sj.judge(_LONG_FOCUS_BASE)
    show("LONG_FOCUS / last_chat=40min", ra)
    ok(50 <= ra["score"] <= 80,          "score 偏中高 (50-80)")
    ok(ra["intent_tier"] != "drop",      "intent_tier 不为 drop")

    # ── 场景 B ────────────────────────────────────────────────────────────────
    print("\n=== 场景 B: LONG_FOCUS，3 分钟前刚主动发过 ===")
    event_b = _event(
        "LONG_FOCUS",
        "她已经在 Code.exe 里连续工作了 26 分钟。",
        minutes_since_last_proactive=3,
    )
    rb = await sj.judge(event_b)
    show("LONG_FOCUS / last_proactive=3min", rb)
    ok(rb["score"] < 40,                 "score 偏低 (<40)")
    ok(rb["intent_tier"] == "drop",      "intent_tier = drop")

    # ── 场景 C ────────────────────────────────────────────────────────────────
    print("\n=== 场景 C: LATE_NIGHT_ACTIVE 凌晨 2 点 ===")
    event_c = _event(
        "LATE_NIGHT_ACTIVE",
        "已经凌晨 2 点了，她还醒着。",
        minutes_since_last_proactive=90,
        minutes_since_last_chat=90,
        local_hour=2,
        focus_app="chrome.exe",
        focus_title_hint="",
        continuous_at_desk_seconds=9000,
        keystroke_density="一般",
        ye_xuan_activity="在浏览网页",
    )
    rc = await sj.judge(event_c)
    show("LATE_NIGHT_ACTIVE / hour=2", rc)
    ok(60 <= rc["score"] <= 85,          "score 中等偏高 (60-85)")

    # ── 场景 D ────────────────────────────────────────────────────────────────
    print("\n=== 场景 D: PRESENCE_RETURNED，离开了 8 分钟 ===")
    event_d = _event(
        "PRESENCE_RETURNED",
        "她回来了，刚离开了 8 分钟。",
        minutes_since_last_proactive=30,
        minutes_since_last_chat=30,
        local_hour=15,
        focus_app="Code.exe",
        focus_title_hint="main.py",
        continuous_at_desk_seconds=3600,
        keystroke_density="稀疏",
        ye_xuan_activity="在思考",
    )
    rd = await sj.judge(event_d)
    show("PRESENCE_RETURNED / away=8min", rd)
    ok(40 <= rd["score"] <= 70,          "score 中等 (40-70)")

    # ── 场景 E ────────────────────────────────────────────────────────────────
    print("\n=== 场景 E: LLM 返回非 JSON → 兜底 drop，不抛异常 ===")
    fake_resp = SimpleNamespace(
        choices=[SimpleNamespace(
            message=SimpleNamespace(content="这不是JSON，随机乱码文字")
        )]
    )
    mock_create = AsyncMock(return_value=fake_resp)
    mock_client = MagicMock()
    mock_client.chat.completions.create = mock_create
    fake_mc = SimpleNamespace(model="test-model", client=mock_client)

    with patch("core.scheduler.sensor_judge.get_model_client", return_value=fake_mc):
        re_ = await sj.judge(_LONG_FOCUS_BASE)

    show("LONG_FOCUS / mock-bad-json", re_)
    ok(re_["score"] == 0,                "score = 0")
    ok(re_["intent_tier"] == "drop",     "intent_tier = drop")
    ok("reason" in re_,                  "返回 dict 包含 reason 字段")

    print("\n=== Smoke 完成 ===\n")


if __name__ == "__main__":
    asyncio.run(main())
