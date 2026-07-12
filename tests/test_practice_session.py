from __future__ import annotations
import json
import pytest

@pytest.mark.asyncio
async def test_bad_review_discards_session(sandbox,monkeypatch):
    from core.growth import practice_session as ps
    interest={"id":"int_x","name":"写诗","domain":"writing","level":1,"status":"active","recent_scores":[],"learning_progress":0}
    monkeypatch.setattr("core.growth.interest_state.active_interests",lambda c:[interest])
    monkeypatch.setattr("core.character_loader.load",lambda c:type("C",(),{"name":"角色","personality":"克制"})())
    replies=iter(["一行作品","not json"])
    async def chat(*a,**k): return next(replies)
    monkeypatch.setattr("core.llm_client.chat",chat)
    assert await ps.run_session({"uid":"u","char_id":"c","interest_id":"int_x"}) is None
    assert ps.load_index("int_x",char_id="c")==[]

@pytest.mark.asyncio
async def test_session_saves_work_score_trace_without_capture(sandbox,monkeypatch):
    from core.growth import practice_session as ps
    interest={"id":"int_y","name":"写诗","domain":"writing","level":1,"status":"active","recent_scores":[],"learning_progress":0,"stalled_since":None}
    monkeypatch.setattr("core.growth.interest_state.active_interests",lambda c:[interest])
    monkeypatch.setattr("core.character_loader.load",lambda c:type("C",(),{"name":"角色","personality":"克制"})())
    async def record(*a,**k): return {**interest,"recent_scores":[6.5],"learning_progress":0}
    monkeypatch.setattr("core.growth.interest_state.record_score",record)
    replies=iter(["窗边一片叶。",json.dumps({"score":6.5,"strengths":["具体"],"one_improvement":"节奏再稳一点"},ensure_ascii=False),json.dumps({"note":None,"replaces":None})])
    async def chat(*a,**k): return next(replies)
    monkeypatch.setattr("core.llm_client.chat",chat)
    traces=[]; monkeypatch.setattr("core.memory.action_trace.record",lambda *a,**k:traces.append(k))
    capture=[]; monkeypatch.setattr("core.memory.fixation_pipeline.capture_turn",lambda *a,**k:capture.append(1))
    result=await ps.run_session({"uid":"u","char_id":"c","interest_id":"int_y"})
    assert result and ps.load_index("int_y",char_id="c")[0]["score"]==6.5
    assert traces and capture==[]

def test_prompt_contains_level_constraint_and_notes(sandbox,monkeypatch):
    from core.growth import notes
    from core.growth.practice_session import build_practice_prompt
    monkeypatch.setattr("core.character_loader.load",lambda c:type("C",(),{"name":"角色","personality":"克制"})())
    monkeypatch.setattr("core.memory.provenance_log.append",lambda *a,**k:None)
    notes.apply_note("int_p","我发现结尾留具体物件",source="s",char_id="c")
    prompt,_=build_practice_prompt({"id":"int_p","name":"写诗","domain":"writing","level":1},char_id="c")
    assert "8行以内" in prompt and "结尾留具体物件" in prompt
