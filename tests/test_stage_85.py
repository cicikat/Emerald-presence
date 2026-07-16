"""Brief 85 · Stage group interaction upgrade: reactions, topic seeds, relation arbitration."""
from __future__ import annotations

import pytest


# ── §5 relation arbitration + recent_moments ────────────────────────────────


def test_arbiter_peer_reply_modulated_by_valence(sandbox):
    from core.stage.arbiter import PEER_REPLY_BASE, score_candidates
    from core.stage.char_relations import _empty_relation, _save_relation
    from core.stage.models import Stage, StageSettings, TranscriptEntry

    stage = Stage(
        "g", "owner", ("yexuan", "yexuanJ-5412"),
        settings=StageSettings(talkativeness={"yexuanJ-5412": 1.0}),
    )
    transcript = [
        TranscriptEntry("owner", "在吗", 1, "t", "user"),
        TranscriptEntry("yexuan", "我在", 2, "t", "user"),
    ]

    baseline = score_candidates(stage, transcript, candidates=["yexuanJ-5412"])[0]
    assert baseline.parts["peer_reply"] == pytest.approx(PEER_REPLY_BASE)

    relation = _empty_relation("yexuan", "yexuanJ-5412")
    relation["b_of_a"]["valence"] = 1.0
    assert _save_relation(relation)
    fond = score_candidates(stage, transcript, candidates=["yexuanJ-5412"])[0]
    assert fond.parts["peer_reply"] == pytest.approx(PEER_REPLY_BASE * 1.2)

    relation["b_of_a"]["valence"] = -1.0
    assert _save_relation(relation)
    cold = score_candidates(stage, transcript, candidates=["yexuanJ-5412"])[0]
    assert cold.parts["peer_reply"] == pytest.approx(PEER_REPLY_BASE * 0.8)


@pytest.mark.asyncio
async def test_relation_handler_rolls_recent_moments_capped_at_five(sandbox, monkeypatch):
    from core.stage.char_relations import handler_update_char_relations, recent_moments

    call_n = {"i": 0}

    async def fake_chat(*args, **kwargs):
        call_n["i"] += 1
        return (
            '{"a_of_b":{"summary":"甲觉得乙靠谱","valence":0.1},'
            '"b_of_a":{"summary":"乙觉得甲随和","valence":0.1},'
            f'"moment":"往事{call_n["i"]}"}}'
        )

    monkeypatch.setattr("core.llm_client.chat", fake_chat)
    for i in range(7):
        await handler_update_char_relations({
            "uid": "owner", "char_a": "yexuan", "char_b": "yexuanJ-5412",
            "excerpt": "甲→乙：回应", "timestamp": 100000.0 + i * 3600 * 7,
            "write_envelope": {"source": "user_chat", "can_write_memory": True},
        })

    assert call_n["i"] == 7
    assert recent_moments("yexuan", "yexuanJ-5412") == [f"往事{i}" for i in range(3, 8)]


def test_recent_moments_backward_compatible_with_old_relation_files(sandbox):
    from core.safe_write import safe_write_json
    from core.sandbox import get_paths
    from core.stage.char_relations import _pair, recent_moments

    char_a, char_b = _pair("yexuan", "yexuanJ-5412")
    old_style = {
        "char_a": char_a, "char_b": char_b,
        "a_of_b": {"summary": "旧摘要", "valence": 0.0, "updated_at": ""},
        "b_of_a": {"summary": "", "valence": 0.0, "updated_at": ""},
        "interaction_count": 1, "last_interaction_ts": 0.0,
    }
    assert safe_write_json(get_paths().char_relation(char_a=char_a, char_b=char_b), old_style)

    assert recent_moments("yexuan", "yexuanJ-5412") == []


def test_directed_block_and_presence_surface_recent_moment(sandbox):
    from core.stage.char_relations import _empty_relation, _save_relation
    from core.stage.context import render_presence
    from core.stage.models import Stage

    relation = _empty_relation("yexuan", "yexuanJ-5412")
    relation["recent_moments"] = ["上次乙帮甲调琴"]
    assert _save_relation(relation)

    stage = Stage("g", "owner", ("yexuan", "yexuanJ-5412"))
    presence = render_presence(stage, viewer_id="yexuan")
    assert "上次乙帮甲调琴" in presence


def _settings(**overrides):
    from core.stage.models import StageSettings

    values = {
        "min_responders": 1,
        "max_responders": 1,
        "max_ai_chain_depth": 0,
        "transcript_limit": 200,
    }
    values.update(overrides)
    return StageSettings(**values)


# ── §3 short reactions ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_phase_r_emits_bounded_short_reactions(sandbox, monkeypatch):
    from core.stage import runner as runner_mod
    from core.stage.arbiter import CandidateScore
    from core.stage.store import create_stage

    create_stage(
        "reaction-group",
        "owner",
        ["yexuan", "yexuanJ-5412", "hongcha"],
        settings=_settings(react_threshold=0.2, speak_threshold=0.5, max_reactions=1),
    )

    def fake_score(stg, transcript, *, candidates=None, derived_keywords=None):
        pool = list(candidates) if candidates is not None else list(stg.roster)
        scores = {"yexuan": 0.9, "yexuanJ-5412": 0.3, "hongcha": 0.3}
        ranked = [CandidateScore(char_id=c, total=scores.get(c, 0.0), parts={}) for c in pool]
        ranked.sort(key=lambda item: -item.total)
        return ranked

    monkeypatch.setattr(runner_mod, "score_candidates", fake_score)

    async def generate_reply(stg, speaker_id, transcript, turn_id, triggered_by):
        return f"{speaker_id}回复"

    reaction_calls: list[str] = []

    async def generate_reaction(stg, speaker_id, transcript, turn_id, triggered_by):
        reaction_calls.append(speaker_id)
        return f"{speaker_id}哈哈"

    result = await runner_mod.run_owner_turn(
        "reaction-group",
        "大家好",
        generate_reply=generate_reply,
        generate_reaction=generate_reaction,
        turn_id="t-react",
    )

    reaction_entries = [e for e in result.replies if e.speaker_id != "yexuan"]
    assert len(reaction_entries) == 1
    assert reaction_entries[0].speaker_id == "yexuanJ-5412"
    assert reaction_entries[0].triggered_by == "yexuan"
    assert reaction_calls == ["yexuanJ-5412"]


@pytest.mark.asyncio
async def test_phase_r_skipped_without_generate_reaction_callback(sandbox, monkeypatch):
    """max_reactions defaults to 2 — old callers that don't wire generate_reaction see no change."""
    from core.stage import runner as runner_mod
    from core.stage.arbiter import CandidateScore
    from core.stage.store import create_stage

    create_stage(
        "reaction-group-legacy",
        "owner",
        ["yexuan", "yexuanJ-5412"],
        settings=_settings(react_threshold=0.0, speak_threshold=1.0),
    )

    def fake_score(stg, transcript, *, candidates=None, derived_keywords=None):
        pool = list(candidates) if candidates is not None else list(stg.roster)
        return [CandidateScore(char_id=c, total=0.9, parts={}) for c in pool]

    monkeypatch.setattr(runner_mod, "score_candidates", fake_score)

    async def generate_reply(stg, speaker_id, transcript, turn_id, triggered_by):
        return f"{speaker_id}回复"

    result = await runner_mod.run_owner_turn(
        "reaction-group-legacy", "大家好", generate_reply=generate_reply, turn_id="t-legacy",
    )

    assert {e.speaker_id for e in result.replies} == {"yexuan"}


@pytest.mark.asyncio
async def test_generate_reaction_truncates_and_caps_tokens(sandbox, monkeypatch):
    from core.stage.models import Stage, TranscriptEntry
    from core.stage.views import StageCharacterView, REACTION_MAX_CHARS

    captured = {}

    async def fake_chat(messages, **kwargs):
        captured["messages"] = messages
        captured["kwargs"] = kwargs
        return "这是一句超过十五个字上限的短反应文本用来测试截断行为"

    monkeypatch.setattr("core.llm_client.chat", fake_chat)

    view = object.__new__(StageCharacterView)
    view.char_id = "yexuanJ-5412"
    from types import SimpleNamespace

    view._character = SimpleNamespace(name="乙", personality="直率", description="")
    stage = Stage("g", "owner", ("yexuan", "yexuanJ-5412"), settings=_settings())
    transcript = [
        TranscriptEntry("owner", "在吗", 1, "t", "user"),
        TranscriptEntry("yexuan", "我在忙", 2, "t", "user"),
    ]

    reaction = await view.generate_reaction(stage, transcript, "t", "yexuan")

    assert len(reaction) <= REACTION_MAX_CHARS
    assert captured["kwargs"]["max_tokens_override"] == 40
    assert captured["kwargs"]["char_id"] == "yexuanJ-5412"
