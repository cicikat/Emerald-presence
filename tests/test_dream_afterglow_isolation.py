"""
tests/test_dream_afterglow_isolation.py — afterglow 摘要文本隔离契约

从 test_dream_mvp1.py 拆出（Brief 50 · 工单D）。v0/v1/v2 均无 afterglow 场景/
动作词剥离、hurt_reluctance 措辞、跨 loader 检索隔离方面的测试，本文件内容
在合并前是唯一覆盖。

Covers:
  - afterglow loader text does not contain scene/action keywords
  - exit_type=hard_exit → afterglow=hurt_reluctance framing
  - afterglow summary not read by episodic/event_log/short_term/mid_term/user_identity loaders
"""

import asyncio
import json
import time

_UID = "dream_test_user"


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Afterglow text does not contain scene/action descriptions
# ═══════════════════════════════════════════════════════════════════════════════

def test_afterglow_text_no_scene_action_keywords(sandbox):
    """Afterglow summary text must not contain scene/action keywords."""
    from core.safe_write import safe_write_json
    from core.dream.dream_state import DREAM_ARTIFACT_SENTINEL

    summaries_dir = sandbox.dreams_summaries_dir()
    summaries_dir.mkdir(parents=True, exist_ok=True)

    # Write a summary with scene/action stripped (should already be stripped by LLM)
    summary = {
        **DREAM_ARTIFACT_SENTINEL,
        "dream_id": "test_dream_001",
        "uid": _UID,
        "created_at": time.time(),
        "exit_type": "soft",
        "title": "光的边缘",
        "summary": "轻柔与依恋",       # Pure emotion, no actions
        "emotional_tags": ["依恋", "温柔", "遗憾"],
        "high_weight_lines": ["（轻轻握住你的手）不想放开"],  # action in raw line
        "symbolic_fragments": ["光", "水", "距离"],
        "summary_weight": 0.7,
        "afterglow": "gentle_residue",
        "reality_boundary": "dream_only",
        "emotional_trace_weight": None,
    }
    safe_write_json(summaries_dir / "dream_test_dream_001.summary.json", summary)

    from core.dream.dream_afterglow import load_afterglow
    text = load_afterglow(_UID)

    assert text, "afterglow should return non-empty text"

    # high_weight_lines must NOT appear in the injected afterglow text
    assert "握住" not in text, "action description leaked into afterglow prompt"
    assert "不想放开" not in text, "raw line leaked into afterglow prompt"

    # Emotional content and prohibition should be present
    assert "梦" in text
    assert "现实" in text or "RP" in text


def test_afterglow_hurt_reluctance_for_hard_exit(sandbox):
    """exit_type=hard_exit → afterglow=hurt_reluctance framing."""
    from core.safe_write import safe_write_json
    from core.dream.dream_state import DREAM_ARTIFACT_SENTINEL

    summaries_dir = sandbox.dreams_summaries_dir()
    summaries_dir.mkdir(parents=True, exist_ok=True)

    summary = {
        **DREAM_ARTIFACT_SENTINEL,
        "dream_id": "test_hard_exit",
        "uid": _UID,
        "created_at": time.time(),
        "exit_type": "hard_exit",
        "title": "中断",
        "summary": "突然的空白",
        "emotional_tags": ["失落"],
        "high_weight_lines": [],
        "symbolic_fragments": [],
        "summary_weight": 0.6,
        "afterglow": "hurt_reluctance",
        "reality_boundary": "dream_only",
        "emotional_trace_weight": None,
    }
    safe_write_json(summaries_dir / "dream_test_hard_exit.summary.json", summary)

    from core.dream.dream_afterglow import load_afterglow
    text = load_afterglow(_UID)

    assert "中断" in text or "强行" in text, "hurt_reluctance frame not applied"


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Afterglow summary not read by reality memory loaders
# ═══════════════════════════════════════════════════════════════════════════════

def test_afterglow_summary_not_retrieved_by_reality_loaders(sandbox):
    """
    dreams/summaries/dream_*.summary.json must never surface in reality loaders.
    Extends the existing isolation contract test to cover the summary path.
    """
    from core.safe_write import safe_write_json
    from core.memory import episodic_memory, event_log, mid_term, short_term, user_identity
    from core.dream.dream_state import DREAM_ARTIFACT_SENTINEL

    sentinel = "AFTERGLOW_ISOLATION_SENTINEL__never_retrieve_contract_v2"

    summaries_dir = sandbox.dreams_summaries_dir()
    summaries_dir.mkdir(parents=True, exist_ok=True)

    safe_write_json(
        summaries_dir / "dream_sentinel_test.summary.json",
        {
            **DREAM_ARTIFACT_SENTINEL,
            "dream_id": "sentinel_test",
            "uid": _UID,
            "summary": sentinel,
            "title": sentinel,
        },
    )

    async def collect():
        return [
            json.dumps(episodic_memory.retrieve(_UID, topic=sentinel, top_k=5)),
            await event_log.search(_UID, sentinel),
            json.dumps(short_term.load_for_prompt(_UID)),
            mid_term.format_for_prompt(_UID),
            json.dumps(await user_identity.load(_UID)),
        ]

    haystacks = asyncio.run(collect())
    assert all(sentinel not in h for h in haystacks), (
        "afterglow summary sentinel found in reality loaders"
    )
