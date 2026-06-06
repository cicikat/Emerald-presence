"""
tests/test_admin_users_profile_scope.py — P1-0E: admin users profile char_id scope

Covers:
1.  GET profile with no char_id uses active_character (active=hongcha).
2.  GET profile with explicit char_id=yexuan reads yexuan bucket (active=hongcha).
3.  GET profile active missing/empty → HTTP 503, user_profile.load not called.
4.  GET profile invalid explicit char_id → HTTP 422, user_profile.load not called.
5.  PUT profile with no char_id writes to active_character (active=hongcha).
6.  PUT profile with explicit char_id=yexuan writes to yexuan bucket (active=hongcha).
7.  Content-level: hongcha route does not return yexuan-only profile content.
8.  DELETE memory with no char_id clears active_character bucket (hongcha).
9.  DELETE memory invalid explicit char_id → HTTP 422, no clear called.
"""

import asyncio
import json
from unittest.mock import MagicMock

import pytest

import core.asset_registry as _reg_mod
from core.asset_registry import AssetRegistry

# Pre-import user_profile at collection time (CWD = project root, config.yaml exists).
# This ensures _CHAR = _char_name() runs before any fixture can chdir to tmp_path.
import core.memory.user_profile as _up_preimport  # noqa: F401


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def chars_tree(tmp_path):
    """Minimal characters/ tree with yexuan + hongcha, plus config.yaml for user_profile."""
    # config.yaml required by user_profile._char_name() on first import
    (tmp_path / "config.yaml").write_text(
        "character:\n  name: 测试角色\n  default: yexuan\n",
        encoding="utf-8",
    )
    chars = tmp_path / "characters"
    chars.mkdir()
    (chars / "yexuan.json").write_text(
        json.dumps({"name": "叶瑄", "description": "test", "world_book": []}),
        encoding="utf-8",
    )
    (chars / "hongcha.json").write_text(
        json.dumps({"name": "红茶", "description": "hongcha test", "world_book": []}),
        encoding="utf-8",
    )
    jb = chars / "reality" / "jailbreaks"
    jb.mkdir(parents=True)
    (jb / "base.json").write_text(json.dumps({"entries": []}), encoding="utf-8")
    return tmp_path


@pytest.fixture
def registry(chars_tree, monkeypatch):
    monkeypatch.chdir(chars_tree)
    reg = AssetRegistry()
    monkeypatch.setattr(_reg_mod, "_registry", reg)
    return reg


def _seed_active(sandbox, char_id: str):
    """Write active_prompt_assets.json with the given char_id."""
    p = sandbox.active_prompt_assets()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps({"active_character": char_id, "enabled_lorebooks": [], "enabled_jailbreaks": []}),
        encoding="utf-8",
    )


def _seed_profile(sandbox, uid: str, char_id: str, data: dict):
    """Write profile.json into the correct char-scoped bucket."""
    import core.memory.user_profile as _up
    _up._save(uid, data, char_id=char_id)


# ── 1: GET profile uses active_character when char_id omitted ─────────────────

def test_get_profile_uses_active_char_when_omitted(sandbox, registry):
    """GET profile with no char_id resolves to active_character (hongcha)."""
    from admin.routers.users import get_user_profile

    _seed_active(sandbox, "hongcha")
    uid = "u_get_profile_active"
    SENTINEL = "草莓大福-hongcha-profile"

    _seed_profile(sandbox, uid, "hongcha", {"name": SENTINEL})

    result = asyncio.run(get_user_profile(uid, char_id=None, auth="dummy"))

    assert result["char_id"] == "hongcha", f"expected char_id=hongcha, got {result['char_id']!r}"
    assert result["profile"]["name"] == SENTINEL, (
        f"hongcha profile name should be sentinel; got {result['profile']['name']!r}"
    )


# ── 2: GET profile with explicit char_id reads that bucket ────────────────────

def test_get_profile_explicit_char_id(sandbox, registry):
    """GET profile with explicit char_id=yexuan reads yexuan bucket (active=hongcha)."""
    from admin.routers.users import get_user_profile

    _seed_active(sandbox, "hongcha")
    uid = "u_get_profile_explicit"
    YEXUAN_NAME = "叶瑄的专属内容"

    _seed_profile(sandbox, uid, "yexuan", {"name": YEXUAN_NAME})

    result = asyncio.run(get_user_profile(uid, char_id="yexuan", auth="dummy"))

    assert result["char_id"] == "yexuan"
    assert result["profile"]["name"] == YEXUAN_NAME, (
        f"yexuan profile should contain yexuan name; got {result['profile']['name']!r}"
    )


# ── 3: GET profile active missing → 503, load not called ─────────────────────

def test_get_profile_missing_active_returns_503(sandbox, registry, monkeypatch):
    """GET profile with no char_id when active_character is empty → HTTP 503."""
    from fastapi import HTTPException
    from admin.routers.users import get_user_profile

    p = sandbox.active_prompt_assets()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps({"active_character": "", "enabled_lorebooks": [], "enabled_jailbreaks": []}),
        encoding="utf-8",
    )

    load_called = []
    import core.memory.user_profile as _up
    monkeypatch.setattr(_up, "load", lambda uid, **kw: load_called.append(kw) or {})

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(get_user_profile("u_get_503", char_id=None, auth="dummy"))

    assert exc_info.value.status_code == 503
    assert not load_called, "user_profile.load must not be called when active_character is invalid"


# ── 4: GET profile invalid explicit char_id → 422, load not called ───────────

def test_get_profile_invalid_char_id_returns_422(sandbox, registry, monkeypatch):
    """GET profile with unknown char_id → HTTP 422, user_profile.load not called."""
    from fastapi import HTTPException
    from admin.routers.users import get_user_profile

    _seed_active(sandbox, "hongcha")

    load_called = []
    import core.memory.user_profile as _up
    monkeypatch.setattr(_up, "load", lambda uid, **kw: load_called.append(kw) or {})

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(get_user_profile("u_get_422", char_id="ghost_char", auth="dummy"))

    assert exc_info.value.status_code == 422
    assert not load_called, "user_profile.load must not be called for invalid char_id"


# ── 5: PUT profile writes to active_character when char_id omitted ────────────

def test_put_profile_uses_active_char_when_omitted(sandbox, registry):
    """PUT profile with no char_id writes into active_character bucket (hongcha)."""
    from admin.routers.users import update_user_profile
    import core.memory.user_profile as _up

    _seed_active(sandbox, "hongcha")
    uid = "u_put_profile_active"
    NEW_VALUE = "红茶的职业"

    result = asyncio.run(
        update_user_profile(uid, {"occupation": NEW_VALUE}, char_id=None, auth="dummy")
    )

    assert result["char_id"] == "hongcha"
    assert result["profile"]["occupation"] == NEW_VALUE

    # Verify the write landed in hongcha bucket, not yexuan
    hongcha_profile = _up.load(uid, char_id="hongcha")
    yexuan_profile = _up.load(uid, char_id="yexuan")

    assert hongcha_profile["occupation"] == NEW_VALUE, (
        f"hongcha bucket should have new occupation; got {hongcha_profile['occupation']!r}"
    )
    assert yexuan_profile["occupation"] != NEW_VALUE, (
        "yexuan bucket must not be modified by hongcha write"
    )


# ── 6: PUT profile with explicit char_id writes to that bucket ────────────────

def test_put_profile_explicit_char_id(sandbox, registry):
    """PUT profile with explicit char_id=yexuan writes to yexuan bucket (active=hongcha)."""
    from admin.routers.users import update_user_profile
    import core.memory.user_profile as _up

    _seed_active(sandbox, "hongcha")
    uid = "u_put_profile_explicit"
    YEXUAN_LOC = "叶瑄住所"

    result = asyncio.run(
        update_user_profile(uid, {"location": YEXUAN_LOC}, char_id="yexuan", auth="dummy")
    )

    assert result["char_id"] == "yexuan"
    assert result["profile"]["location"] == YEXUAN_LOC

    # Verify isolation: hongcha bucket untouched
    yexuan_profile = _up.load(uid, char_id="yexuan")
    hongcha_profile = _up.load(uid, char_id="hongcha")

    assert yexuan_profile["location"] == YEXUAN_LOC
    assert hongcha_profile["location"] != YEXUAN_LOC, (
        "hongcha bucket must not receive yexuan write"
    )


# ── 7: Content-level isolation ────────────────────────────────────────────────

def test_get_profile_content_isolation(sandbox, registry):
    """GET profile for hongcha does not return yexuan-only sentinel content."""
    from admin.routers.users import get_user_profile

    _seed_active(sandbox, "hongcha")
    uid = "u_content_isolation"
    YEXUAN_ONLY = "叶瑄专属关键词_唯一标识符XYZ"
    HONGCHA_ONLY = "红茶专属关键词_唯一标识符ABC"

    _seed_profile(sandbox, uid, "yexuan", {"name": YEXUAN_ONLY})
    _seed_profile(sandbox, uid, "hongcha", {"name": HONGCHA_ONLY})

    hongcha_result = asyncio.run(get_user_profile(uid, char_id=None, auth="dummy"))
    yexuan_result = asyncio.run(get_user_profile(uid, char_id="yexuan", auth="dummy"))

    profile_text_hongcha = json.dumps(hongcha_result["profile"], ensure_ascii=False)
    profile_text_yexuan = json.dumps(yexuan_result["profile"], ensure_ascii=False)

    assert YEXUAN_ONLY not in profile_text_hongcha, (
        "hongcha profile must not contain yexuan-only sentinel"
    )
    assert HONGCHA_ONLY not in profile_text_yexuan, (
        "yexuan profile must not contain hongcha-only sentinel"
    )
    assert HONGCHA_ONLY in profile_text_hongcha
    assert YEXUAN_ONLY in profile_text_yexuan


# ── 8: DELETE memory uses active_character when char_id omitted ───────────────

def test_delete_memory_uses_active_char_when_omitted(sandbox, registry, monkeypatch):
    """DELETE memory with no char_id clears active_character (hongcha) bucket only."""
    from admin.routers.users import delete_user_memory
    from core.memory import short_term as _st
    import core.memory.user_profile as _up

    _seed_active(sandbox, "hongcha")
    uid = "u_delete_active"
    SENTINEL_H = "草莓大福-delete-hongcha"
    SENTINEL_Y = "草莓大福-delete-yexuan"

    _st.append(uid, "user", SENTINEL_H, char_id="hongcha")
    _st.append(uid, "user", SENTINEL_Y, char_id="yexuan")
    _seed_profile(sandbox, uid, "hongcha", {"name": "hongcha_name"})
    _seed_profile(sandbox, uid, "yexuan", {"name": "yexuan_name"})

    result = asyncio.run(delete_user_memory(uid, char_id=None, auth="dummy"))

    assert result["char_id"] == "hongcha"

    # hongcha short-term cleared
    assert _st.load(uid, char_id="hongcha") == [], "hongcha short-term must be empty"
    # yexuan short-term untouched
    assert any(SENTINEL_Y in m.get("content", "") for m in _st.load(uid, char_id="yexuan")), (
        "yexuan short-term must be untouched"
    )

    # hongcha profile cleared (reset to default)
    hongcha_profile = _up.load(uid, char_id="hongcha")
    assert hongcha_profile["name"] is None, "hongcha profile must be reset to default"

    # yexuan profile untouched
    yexuan_profile = _up.load(uid, char_id="yexuan")
    assert yexuan_profile["name"] == "yexuan_name", "yexuan profile must be untouched"


# ── 9: DELETE memory invalid char_id → 422, no clear called ──────────────────

def test_delete_memory_invalid_char_id_returns_422(sandbox, registry, monkeypatch):
    """DELETE memory with unknown char_id → HTTP 422, short_term.clear not called."""
    from fastapi import HTTPException
    from admin.routers.users import delete_user_memory

    _seed_active(sandbox, "hongcha")

    clear_called = []
    import core.memory.short_term as _st
    monkeypatch.setattr(_st, "clear", lambda uid, **kw: clear_called.append(kw))

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(delete_user_memory("u_del_422", char_id="bad_char", auth="dummy"))

    assert exc_info.value.status_code == 422
    assert not clear_called, "short_term.clear must not be called for invalid char_id"
