"""
tests/test_dream_memory_access_tiers.py — memory_access 档位（card_only /
relationship_summary / full_snapshot）契约

合并自 test_dream_v0.py + test_dream_mvp1.py 中未被去重的 memory_access 测试
（Brief 50 · 工单D）。v0 覆盖 relationship_summary 档、legacy 迁移、dream_turn
期间 live recall 门禁（不同调用点）；mvp1 覆盖 card_only/full_snapshot 档在
build_snapshot 快照构造点的行为，且预置了真实数据（比 v0 对应测试更强，v0 中
重复的部分已删除）。

Covers:
  - memory_access=card_only → 快照 episodic/midterm/profile 字段清空 + episodic
    retrieve 不被调用（真实预置数据下验证）
  - memory_access=full_snapshot → episodic retrieve 被调用（快照级）
  - memory_access=relationship_summary → episodic/midterm 不被调用（v0 独有档位）
  - legacy amnesia/keep_impression 迁移到新 memory_access 枚举
  - dream_turn 期间任何档位都不触发 live episodic retrieve（不同于快照构造点）
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_UID = "v0_test_user"

_FAKE_CHARACTER = MagicMock()
_FAKE_CHARACTER.name = "Companion"
_FAKE_CHARACTER.description = "Companion，男，圣塞西尔学院教师，温柔内敛，有强烈的依恋倾向。"
_FAKE_CHARACTER.gender = "male"
_FAKE_CHARACTER.jailbreak_entries = []

_FAKE_PIPELINE = MagicMock()
_FAKE_PIPELINE.character = _FAKE_CHARACTER
_FAKE_PIPELINE.lore_engine = MagicMock()
_FAKE_PIPELINE.lore_engine.match.return_value = ([], [])


def _make_fake_llm(reply: str = "梦境回复文本") -> AsyncMock:
    return AsyncMock(return_value=reply)


@pytest.fixture
def active_dream(sandbox):
    from core.dream.dream_state import write_state, DreamStatus
    state = {
        "user_id": _UID,
        "status": DreamStatus.DREAM_ACTIVE.value,
        "dream_id": f"dream_{_UID}_v0test",
        "context_snapshot": {
            "created_at": time.time(),
            "user_id": _UID,
            "yexuan_awareness": "lucid_shared",
            "boundary": "dream_only",
            "entry_reason": "v0 unit test",
            "memory_access": "relationship_summary",
            "relationship_state": {},
            "recent_reality_context": "",
            "episodic_summary": "",
            "mid_term_context": "",
            "profile_impression": "",
        },
    }
    write_state(_UID, state)
    return state


# ═══════════════════════════════════════════════════════════════════════════════
# card_only / full_snapshot：build_snapshot 快照构造点（来自 mvp1，含真实预置数据）
# ═══════════════════════════════════════════════════════════════════════════════

def test_card_only_empties_memory_fields_in_snapshot(sandbox):
    """memory_access=card_only → episodic_summary and mid_term_context empty in snapshot."""
    from core.dream.dream_settings import save as _save
    _save(_UID, {"memory_access": "card_only"})

    # Plant fake episodic and mid-term data
    from core.memory import mid_term
    mid_term.append(_UID, "用户最近很开心", tags=[])

    episodic_called = []

    def fake_retrieve(*a, **kw):
        episodic_called.append(True)
        return []

    async def run():
        with patch("core.memory.episodic_memory.retrieve", fake_retrieve):
            from core.dream.dream_context import build_snapshot
            return await build_snapshot(_UID, entry_reason="test card_only")

    snapshot = asyncio.run(run())

    assert snapshot["episodic_summary"] == "", "card_only should give empty episodic"
    assert snapshot["mid_term_context"] == "", "card_only should give empty mid_term"
    assert not episodic_called, "episodic retrieve called despite memory_access=card_only"


def test_full_snapshot_includes_episodic_in_snapshot(sandbox):
    """memory_access=full_snapshot → snapshot-level episodic fetch is attempted."""
    from core.dream.dream_settings import save as _save
    _save(_UID, {"memory_access": "full_snapshot"})

    episodic_called = []

    def fake_retrieve(*a, **kw):
        episodic_called.append(True)
        return []

    async def run():
        with patch("core.memory.episodic_memory.retrieve", fake_retrieve):
            with patch("core.memory.mood_state.get_current", return_value="neutral"):
                from core.dream.dream_context import build_snapshot
                return await build_snapshot(_UID, entry_reason="test full_snapshot")

    asyncio.run(run())
    assert episodic_called, "full_snapshot should call episodic retrieve for snapshot"


def test_card_only_empties_profile_impression(sandbox):
    """memory_access=card_only → profile_impression empty in snapshot."""
    from core.dream.dream_settings import save as _save
    _save(_UID, {"memory_access": "card_only"})

    # Plant profile data
    from core.memory import user_profile
    user_profile.save(_UID, {"traits": ["开朗", "有趣"]})

    async def run():
        from core.dream.dream_context import build_snapshot
        return await build_snapshot(_UID)

    snapshot = asyncio.run(run())
    assert snapshot["profile_impression"] == "", "card_only should give empty profile_impression"


# ═══════════════════════════════════════════════════════════════════════════════
# relationship_summary（来自 v0，mvp1 未覆盖此档位）
# ═══════════════════════════════════════════════════════════════════════════════

def test_memory_access_relationship_summary_no_episodic(sandbox):
    """memory_access=relationship_summary → episodic/midterm 不被调用。"""
    from core.dream.dream_settings import save as _save
    _save(_UID, {"memory_access": "relationship_summary"})

    episodic_called = []

    def fake_retrieve(*a, **kw):
        episodic_called.append(True)
        return []

    async def run():
        with patch("core.memory.episodic_memory.retrieve", fake_retrieve):
            from core.dream.dream_context import build_snapshot
            return await build_snapshot(_UID)

    asyncio.run(run())
    assert not episodic_called, "episodic called despite memory_access=relationship_summary"


# ═══════════════════════════════════════════════════════════════════════════════
# legacy amnesia/keep_impression → memory_access 迁移（来自 v0，mvp1 未覆盖）
# ═══════════════════════════════════════════════════════════════════════════════

def test_memory_access_migration_amnesia_true_gives_card_only(sandbox):
    """legacy amnesia=True 迁移 → memory_access=card_only。"""
    from core.dream.dream_settings import load as _load
    from core.safe_write import safe_write_json
    from core.sandbox import get_paths
    path = get_paths().dream_settings_path(_UID)
    path.parent.mkdir(parents=True, exist_ok=True)
    safe_write_json(path, {"amnesia": True, "keep_impression": True})

    settings = _load(_UID)
    assert settings["memory_access"] == "card_only", (
        f"amnesia=True should migrate to card_only, got {settings['memory_access']}"
    )


def test_memory_access_migration_keep_impression_true_gives_relationship_summary(sandbox):
    """legacy amnesia=False + keep_impression=True → memory_access=relationship_summary。"""
    from core.safe_write import safe_write_json
    from core.sandbox import get_paths
    from core.dream.dream_settings import load as _load

    path = get_paths().dream_settings_path(_UID)
    path.parent.mkdir(parents=True, exist_ok=True)
    safe_write_json(path, {"amnesia": False, "keep_impression": True})

    settings = _load(_UID)
    assert settings["memory_access"] == "relationship_summary", (
        f"amnesia=False+keep_impression=True should migrate to relationship_summary, "
        f"got {settings['memory_access']}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# dream_turn 期间 live recall 门禁（来自 v0：不同于快照构造点的调用点）
# ═══════════════════════════════════════════════════════════════════════════════

def test_memory_access_no_live_recall_during_dream_turn(sandbox, active_dream):
    """dream_turn 期间任何 memory_access 档位都不触发 live retrieve。"""
    live_retrieve_called = []

    def fake_retrieve(*a, **kw):
        live_retrieve_called.append(True)
        return []

    with patch("core.llm_client.chat", _make_fake_llm()), \
         patch("core.pipeline_registry.get", return_value=_FAKE_PIPELINE), \
         patch("core.memory.episodic_memory.retrieve", fake_retrieve):
        from core.dream import dream_pipeline
        asyncio.run(dream_pipeline.dream_turn(_UID, "你好"))

    assert not live_retrieve_called, "live episodic retrieve called during dream turn"
