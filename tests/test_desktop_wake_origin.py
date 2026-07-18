"""
tests/test_desktop_wake_origin.py — desktop_wake origin tagging (fix for round6 miss)

Verifies that desktop_wake Path B:
1. Calls set_capture_origin with origin="proactive", trigger_name="desktop_wake"
   before build_prompt, so the prompt_capture snapshot is correctly tagged.
2. Calls update_llm_output with the LLM reply after run_llm, so the snapshot
   has a paired output visible in the inspector.
3. Does NOT call set_capture_origin or update_llm_output when the perceive_event
   gate rejects the request (not-accepted path).

Note on isolation: test_prompt_capture_origin.py stubs core.config_loader and
core.sandbox in sys.modules.  We patch via direct module-object references
(not string dotted-paths) so these tests are immune to that stub ordering.
"""

import asyncio
import json
import sys
import types
import pytest


# ── ensure minimal stubs exist before any import that needs them ───────────────
# test_prompt_capture_origin.py may have already inserted empty stubs for
# core.config_loader and core.sandbox.  We fill in the attributes that the
# real modules would provide so downstream imports don't fail.

def _ensure_stub(name: str):
    if name not in sys.modules:
        sys.modules[name] = types.ModuleType(name)


_ensure_stub("core.config_loader")
_ensure_stub("core.sandbox")

# core.sandbox: provide get_paths and safe_user_id if missing
_sb_stub = sys.modules["core.sandbox"]
if not hasattr(_sb_stub, "get_paths"):
    class _StubDataPaths:
        def __getattr__(self, item):
            raise NotImplementedError(f"stub DataPaths.{item} not set for test")

    _sb_stub.get_paths = lambda: _StubDataPaths()
    _sb_stub.safe_user_id = lambda uid: uid
    _sb_stub.DataPaths = _StubDataPaths

# ── shared pipeline stub ──────────────────────────────────────────────────────

class _FakePipeline:
    character = type("C", (), {"name": "Companion"})()

    def _current_reality_scope(self, uid):
        from core.memory.scope import MemoryScope
        return MemoryScope.reality_scope(uid, "char-a")

    async def fetch_context(self, uid, prompt, *a, **kw):
        return {}

    def build_prompt(self, uid, prompt, context, **kw):
        return [], {}

    async def run_llm(self, messages):
        return "上线问候内容"

    async def post_process_critical(self, uid, content, reply, **kwargs):
        return {"turn_id": "t-wake", "critical_written": True, "emotion": "neutral"}

    async def post_process_slow(self, uid, content, reply, critical_result, **kwargs):
        return {"emotion": "neutral", "turn_id": critical_result.get("turn_id")}


def _patch_common(monkeypatch, pipeline=None, rpe_accepted=True):
    """
    Patch external dependencies so desktop_wake Path B can run.
    Uses direct module-object references to avoid string-path monkeypatch failures
    when upstream test files have already put stubs into sys.modules.
    """
    import core.pipeline_registry as _preg
    monkeypatch.setattr(_preg, "_pipeline", pipeline or _FakePipeline())

    # Patch config_loader via its module object; raising=False because the stub
    # set by test_prompt_capture_origin may not have get_config yet.
    import core.config_loader as _cl
    monkeypatch.setattr(_cl, "get_config", lambda: {"scheduler": {"owner_id": "owner-wake"}}, raising=False)

    import core.perceive_event as _pe_mod
    monkeypatch.setattr(_pe_mod, "_resolve_char_id", lambda uid, cid: "char-a")

    # 5 条真实用户轮，模拟老用户重开——这些用例测的是 capture_origin 记账，不是
    # Brief 97 的冷启动首见种子分支（见 test_desktop_wake_origin_seed_prompt_is_wake_text）。
    import core.memory.short_term as _st
    monkeypatch.setattr(_st, "load", lambda uid, char_id=None: [{"role": "user", "content": "hi"}] * 5)

    import core.response_processor as _rp
    monkeypatch.setattr(_rp, "strip_render_tags", lambda s: s)

    import core.reality_output_guard as _rog
    monkeypatch.setattr(_rog, "clean_reality_reply_text", lambda text, name: text)

    import channels.desktop_ws as _dws
    monkeypatch.setattr(_dws, "get_connect_time", lambda: 0.0)
    monkeypatch.setattr(_dws, "is_connected", lambda: False)

    async def fake_record(**kwargs):
        from core.turn_sink import TurnResult
        return TurnResult(turn_id="t-wake-001", written_to_memory=True, fanout_targets=[])

    import core.turn_sink as _ts
    monkeypatch.setattr(_ts, "record_assistant_turn", fake_record)

    # Path A: no eligible pending trigger → fall to Path B
    import core.sandbox as _sb

    class _FakeAPA:
        def read_text(self, encoding="utf-8"):
            return json.dumps({"active_character": "char-a"})

    class _FakeDataPaths:
        def active_prompt_assets(self):
            return _FakeAPA()

    monkeypatch.setattr(_sb, "DataPaths", _FakeDataPaths)

    # Clear dedup so each test starts fresh
    from core.perceive_event import clear_dedup_registry_for_test
    clear_dedup_registry_for_test()

    # Patch receive_perceive_event to bypass dream_state import chain
    if rpe_accepted:
        from core.perceive_event import PerceiveStatus, PerceiveResult

        async def _always_accept(event):
            return PerceiveResult(
                status=PerceiveStatus.ACCEPTED,
                reason="test_forced_accept",
                event_id="eid-test",
                dedupe_key="dk-test",
            )

        monkeypatch.setattr(_pe_mod, "receive_perceive_event", _always_accept)


# ─────────────────────────────────────────────────────────────────────────────
# Test 1: set_capture_origin called with correct proactive origin
# ─────────────────────────────────────────────────────────────────────────────

async def test_desktop_wake_path_b_calls_set_capture_origin(monkeypatch):
    """Path B must call set_capture_origin(origin='proactive', trigger_name='desktop_wake')."""
    _patch_common(monkeypatch)

    captured_origins: list[dict] = []

    import core.observe.prompt_capture as _pc

    def _spy_set(info: dict):
        captured_origins.append(info)

    monkeypatch.setattr(_pc, "set_capture_origin", _spy_set)

    from admin.routers.chat import desktop_wake
    result = await desktop_wake({})

    assert result.get("source") == "live_wake", f"expected live_wake, got {result}"
    assert len(captured_origins) == 1, (
        f"set_capture_origin should be called exactly once; got {captured_origins}"
    )
    origin = captured_origins[0]
    assert origin["origin"] == "proactive"
    assert origin["trigger_name"] == "desktop_wake"
    assert "seed_prompt" in origin
    assert "search_query" in origin


# ─────────────────────────────────────────────────────────────────────────────
# Test 2: update_llm_output called with the LLM reply
# ─────────────────────────────────────────────────────────────────────────────

async def test_desktop_wake_path_b_calls_update_llm_output(monkeypatch):
    """Path B must call update_llm_output(uid, reply) after run_llm."""
    _patch_common(monkeypatch)

    output_calls: list[tuple] = []

    import core.observe.prompt_capture as _pc

    def _spy_update(uid: str, reply: str):
        output_calls.append((uid, reply))

    monkeypatch.setattr(_pc, "update_llm_output", _spy_update)

    from admin.routers.chat import desktop_wake
    result = await desktop_wake({})

    assert result.get("source") == "live_wake", f"expected live_wake, got {result}"
    assert len(output_calls) == 1, (
        f"update_llm_output should be called exactly once; got {output_calls}"
    )
    uid_arg, reply_arg = output_calls[0]
    assert reply_arg == "上线问候内容"
    assert uid_arg  # uid is non-empty


# ─────────────────────────────────────────────────────────────────────────────
# Test 3: origin fields — seed_prompt contains the wake seed text
# ─────────────────────────────────────────────────────────────────────────────

async def test_desktop_wake_origin_seed_prompt_is_wake_text(monkeypatch):
    """seed_prompt in origin must contain the actual wake seed text."""
    _patch_common(monkeypatch)

    captured_origins: list[dict] = []

    import core.observe.prompt_capture as _pc

    def _spy(info: dict):
        captured_origins.append(info)

    monkeypatch.setattr(_pc, "set_capture_origin", _spy)

    from admin.routers.chat import desktop_wake
    await desktop_wake({})

    assert captured_origins, "set_capture_origin was not called"
    seed = captured_origins[0].get("seed_prompt", "")
    assert "桌宠" in seed or "重新打开" in seed, (
        f"seed_prompt should reference the wake scenario; got {seed!r}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Test 3b（Brief 97 §4）：真实用户轮数为 0（冷启动首次打开）时，种子换成首见版，
# 且必须带"不要假装拥有与用户过去的记忆"这句防幻觉约束。
# ─────────────────────────────────────────────────────────────────────────────

async def test_desktop_wake_origin_seed_prompt_is_first_open_text_when_no_history(monkeypatch):
    _patch_common(monkeypatch)

    import core.memory.short_term as _st
    monkeypatch.setattr(_st, "load", lambda uid, char_id=None: [])

    captured_origins: list[dict] = []

    import core.observe.prompt_capture as _pc

    def _spy(info: dict):
        captured_origins.append(info)

    monkeypatch.setattr(_pc, "set_capture_origin", _spy)

    from admin.routers.chat import desktop_wake
    await desktop_wake({})

    assert captured_origins, "set_capture_origin was not called"
    seed = captured_origins[0].get("seed_prompt", "")
    assert "第一次打开" in seed
    assert "不要假装拥有与用户过去的记忆" in seed
    assert "重新打开" not in seed


# ─────────────────────────────────────────────────────────────────────────────
# Test 4: gate-rejected path does NOT call set_capture_origin
# ─────────────────────────────────────────────────────────────────────────────

async def test_desktop_wake_gate_rejected_no_origin_call(monkeypatch):
    """When perceive_event gate rejects, set_capture_origin must NOT be called."""
    _patch_common(monkeypatch, rpe_accepted=False)

    from core.perceive_event import PerceiveStatus, PerceiveResult
    import core.perceive_event as _pe_mod

    async def _always_reject(event):
        return PerceiveResult(
            status=PerceiveStatus.DUPLICATE,
            reason="test_forced_duplicate",
            event_id="eid-rej",
            dedupe_key="dk-rej",
        )

    monkeypatch.setattr(_pe_mod, "receive_perceive_event", _always_reject)

    origin_calls: list[dict] = []

    import core.observe.prompt_capture as _pc

    def _spy(info: dict):
        origin_calls.append(info)

    monkeypatch.setattr(_pc, "set_capture_origin", _spy)

    from admin.routers.chat import desktop_wake
    result = await desktop_wake({})

    assert result.get("source") == "duplicate_wake", f"expected duplicate_wake, got {result}"
    assert origin_calls == [], (
        f"set_capture_origin must not be called when gate rejects; got {origin_calls}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Test 5: update_llm_output NOT called when LLM returns empty
# ─────────────────────────────────────────────────────────────────────────────

async def test_desktop_wake_no_update_output_when_llm_empty(monkeypatch):
    """If run_llm returns empty string, update_llm_output must NOT be called."""

    class _EmptyLLMPipeline(_FakePipeline):
        async def run_llm(self, messages):
            return ""

    _patch_common(monkeypatch, pipeline=_EmptyLLMPipeline())

    output_calls: list[tuple] = []

    import core.observe.prompt_capture as _pc

    def _spy_update(uid: str, reply: str):
        output_calls.append((uid, reply))

    monkeypatch.setattr(_pc, "update_llm_output", _spy_update)

    from admin.routers.chat import desktop_wake
    result = await desktop_wake({})

    assert result.get("source") == "live_wake_empty"
    assert output_calls == [], (
        f"update_llm_output must not be called when LLM returns empty; got {output_calls}"
    )
