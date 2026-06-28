"""Tests for prompt_capture origin tagging (A + B scope from admin-panel-round6 work order)."""

import asyncio
import sys
import types
import pytest

# ─── minimal stubs so prompt_capture imports cleanly without the full app ──

for mod in (
    "core.config_loader",
    "core.sandbox",
):
    if mod not in sys.modules:
        sys.modules[mod] = types.ModuleType(mod)


def _make_capture():
    """Re-import a fresh prompt_capture module (avoids ring pollution between tests)."""
    import importlib
    import core.observe.prompt_capture as pc
    importlib.reload(pc)
    return pc


# ─────────────────────────────────────────────────────────────────────────────
# helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_msg(layer="1_system_prompt", content="hello", **kw):
    return {"role": "system", "content": content, "_layer": layer, **kw}


def _do_capture(pc, uid="u1", layers=None, origin=None):
    if origin is not None:
        pc.set_capture_origin(origin)
    msgs = layers or [_make_msg()]
    meta = {"token_estimate": len(msgs[0]["content"]), "removed_layers": [], "tags": []}
    pc.capture(uid, msgs, meta)


# ─────────────────────────────────────────────────────────────────────────────
# A-1  default origin is {"origin": "user"}
# ─────────────────────────────────────────────────────────────────────────────

def test_default_origin_is_user():
    pc = _make_capture()
    _do_capture(pc, uid="u1")
    snap = pc.get_snapshots("u1")[-1]
    assert snap["origin"] == {"origin": "user"}


# ─────────────────────────────────────────────────────────────────────────────
# A-2  set_capture_origin persists to snapshot
# ─────────────────────────────────────────────────────────────────────────────

def test_set_origin_desktop():
    pc = _make_capture()
    _do_capture(pc, uid="u2", origin={"origin": "desktop"})
    snap = pc.get_snapshots("u2")[-1]
    assert snap["origin"]["origin"] == "desktop"


def test_set_origin_proactive_full():
    pc = _make_capture()
    info = {
        "origin": "proactive",
        "trigger_name": "random_message",
        "seed_prompt": "想说点什么",
        "search_query": "",
    }
    _do_capture(pc, uid="u3", origin=info)
    snap = pc.get_snapshots("u3")[-1]
    assert snap["origin"]["origin"] == "proactive"
    assert snap["origin"]["trigger_name"] == "random_message"
    assert snap["origin"]["seed_prompt"] == "想说点什么"


# ─────────────────────────────────────────────────────────────────────────────
# A-3  consecutive captures with explicit distinct origins both stick
# ─────────────────────────────────────────────────────────────────────────────

def test_consecutive_origins_explicit():
    # ContextVar persists within the same sync context, so each caller must
    # set its own origin.  This test verifies two explicit values both work.
    pc = _make_capture()
    _do_capture(pc, uid="u4", origin={"origin": "desktop"})
    _do_capture(pc, uid="u4", origin={"origin": "user"})  # reset explicitly
    snaps = pc.get_snapshots("u4")
    assert snaps[0]["origin"]["origin"] == "desktop"
    assert snaps[1]["origin"]["origin"] == "user"


# ─────────────────────────────────────────────────────────────────────────────
# A-4  set_capture_origin in async context (contextvar isolation across tasks)
# ─────────────────────────────────────────────────────────────────────────────

def test_async_origin_isolation():
    """Two concurrent async tasks must not bleed origin into each other."""
    pc = _make_capture()

    results = {}

    async def task_proactive():
        pc.set_capture_origin({"origin": "proactive", "trigger_name": "morning_greeting"})
        await asyncio.sleep(0)  # yield so the other task can run
        pc.capture("ua", [_make_msg()], {"token_estimate": 5, "removed_layers": [], "tags": []})
        results["proactive"] = pc.get_snapshots("ua")[-1]["origin"]

    async def task_user():
        # no set_capture_origin → default
        await asyncio.sleep(0)
        pc.capture("ub", [_make_msg()], {"token_estimate": 5, "removed_layers": [], "tags": []})
        results["user"] = pc.get_snapshots("ub")[-1]["origin"]

    async def run():
        await asyncio.gather(task_proactive(), task_user())

    asyncio.run(run())
    assert results["proactive"]["origin"] == "proactive"
    assert results["user"]["origin"] == "user"


# ─────────────────────────────────────────────────────────────────────────────
# A-5  update_llm_output pairs with latest snapshot
# ─────────────────────────────────────────────────────────────────────────────

def test_update_llm_output():
    pc = _make_capture()
    _do_capture(pc, uid="u5", origin={"origin": "proactive", "trigger_name": "daily_journal"})
    assert pc.get_snapshots("u5")[-1]["llm_output"] is None
    pc.update_llm_output("u5", "回复内容")
    assert pc.get_snapshots("u5")[-1]["llm_output"] == "回复内容"


# ─────────────────────────────────────────────────────────────────────────────
# C-1  get_latest_proactive_by_trigger ignores non-proactive snapshots
# ─────────────────────────────────────────────────────────────────────────────

def test_catalog_empty_without_proactive():
    pc = _make_capture()
    _do_capture(pc, uid="u6")  # user origin
    assert pc.get_latest_proactive_by_trigger() == {}


def test_catalog_returns_trigger_keyed_dict():
    pc = _make_capture()
    _do_capture(pc, uid="u7", origin={
        "origin": "proactive", "trigger_name": "morning_greeting",
        "seed_prompt": "早上好", "search_query": "",
    })
    _do_capture(pc, uid="u7", origin={
        "origin": "proactive", "trigger_name": "random_message",
        "seed_prompt": "随机消息", "search_query": "",
    })
    catalog = pc.get_latest_proactive_by_trigger()
    assert "morning_greeting" in catalog
    assert "random_message" in catalog
    assert catalog["morning_greeting"]["origin"]["seed_prompt"] == "早上好"


def test_catalog_picks_newest_for_same_trigger():
    pc = _make_capture()
    _do_capture(pc, uid="u8", origin={
        "origin": "proactive", "trigger_name": "daily_journal",
        "seed_prompt": "第一次", "search_query": "今天",
    })
    _do_capture(pc, uid="u8", origin={
        "origin": "proactive", "trigger_name": "daily_journal",
        "seed_prompt": "第二次（更新）", "search_query": "今天",
    })
    catalog = pc.get_latest_proactive_by_trigger()
    assert "daily_journal" in catalog
    assert catalog["daily_journal"]["origin"]["seed_prompt"] == "第二次（更新）"


def test_catalog_trigger_name_empty_excluded():
    pc = _make_capture()
    _do_capture(pc, uid="u9", origin={
        "origin": "proactive", "trigger_name": "",  # no trigger name
        "seed_prompt": "x", "search_query": "",
    })
    catalog = pc.get_latest_proactive_by_trigger()
    assert catalog == {}


# ─────────────────────────────────────────────────────────────────────────────
# C-2  list_uids includes uid with any snapshot
# ─────────────────────────────────────────────────────────────────────────────

def test_list_uids_after_proactive():
    pc = _make_capture()
    _do_capture(pc, uid="u10", origin={
        "origin": "proactive", "trigger_name": "overflow",
        "seed_prompt": "x", "search_query": "",
    })
    assert "u10" in pc.list_uids()
