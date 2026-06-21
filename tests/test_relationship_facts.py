"""
tests/test_relationship_facts.py

MVP acceptance tests for relationship_facts (dynamic lorebook):
  1. Manual confirmed entry -> keyword match -> appears in lore_entries
  2. Address suggester produces pending entries with evidence source
  3. pending entries are NEVER returned by match() (never injected)
  4. confirm -> injectable; reject -> archived, not injectable
  5. path_resolver returns correct S6 path for relationship_facts
"""

import datetime
import yaml
import pytest


# ── sandbox fixture ──────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def sandbox(tmp_path, monkeypatch):
    import core.data_paths as dp
    import core.sandbox as sb

    instance = dp.DataPaths.__new__(dp.DataPaths)
    instance.mode = "test"
    instance.test_session_id = "pytest"
    instance._base = tmp_path

    monkeypatch.setattr(sb, "_instance", instance)
    monkeypatch.setattr(dp, "_DEFAULT_CHAR_ID", "testchar")

    assets_path = tmp_path / "runtime" / "active_prompt_assets.json"
    assets_path.parent.mkdir(parents=True, exist_ok=True)
    import json
    assets_path.write_text(
        json.dumps({"active_character": "testchar", "enabled_lorebooks": []}),
        encoding="utf-8",
    )
    return tmp_path


# ── helpers ──────────────────────────────────────────────────────────────────

def _write_event_log(tmp_path, uid, char_id, date_str, user_messages):
    d = tmp_path / "runtime" / "memory" / char_id / uid / "event_log"
    d.mkdir(parents=True, exist_ok=True)
    lines = [f"**用户**：{msg}" for msg in user_messages]
    (d / f"{date_str}.md").write_text("\n".join(lines), encoding="utf-8")


# ── 1. path_resolver ─────────────────────────────────────────────────────────

def test_path_resolver_returns_s6_path(sandbox):
    from core.memory.scope import MemoryScope
    from core.memory.path_resolver import resolve_path

    scope = MemoryScope.reality_scope("u123", "testchar")
    p = resolve_path(scope, "relationship_facts")
    assert p == sandbox / "runtime" / "memory" / "testchar" / "u123" / "relationship_facts.yaml"


def test_path_resolver_rejects_unknown_artifact(sandbox):
    from core.memory.scope import MemoryScope
    from core.memory.path_resolver import resolve_path

    scope = MemoryScope.reality_scope("u1", "testchar")
    with pytest.raises(ValueError, match="unknown artifact"):
        resolve_path(scope, "no_such_artifact_xyz")


# ── 2. load / save ───────────────────────────────────────────────────────────

def test_load_returns_empty_when_missing(sandbox):
    from core.relationship_facts import load

    assert load("u1", char_id="testchar") == []


def test_save_and_load_roundtrip(sandbox):
    from core.relationship_facts import load, save

    facts = [
        {
            "keywords": ["owner"],
            "content":  "User calls char 'owner'.",
            "enabled":  True,
            "status":   "confirmed",
            "confidence": 0.9,
            "source":   "manual",
            "first_seen": "2026-01-01",
            "last_seen":  "2026-06-20",
            "hit_count":  10,
            "insertion_order": 60,
        }
    ]
    save("u1", facts, char_id="testchar")
    loaded = load("u1", char_id="testchar")
    assert len(loaded) == 1
    assert loaded[0]["keywords"] == ["owner"]
    assert loaded[0]["status"] == "confirmed"


# ── 3. match() — confirmed entries ───────────────────────────────────────────

def test_match_confirmed_entry_hits(sandbox):
    from core.relationship_facts import save, match

    save("u1", [
        {
            "keywords": ["zuoren"],
            "content":  "hit content here",
            "enabled":  True,
            "status":   "confirmed",
            "insertion_order": 60,
        }
    ], char_id="testchar")

    results = match("u1", "zuoren nice to meet you", char_id="testchar")
    assert results == ["hit content here"]


def test_match_returns_empty_when_no_keyword_hit(sandbox):
    from core.relationship_facts import save, match

    save("u1", [
        {
            "keywords": ["specialkw"],
            "content":  "special content",
            "enabled":  True,
            "status":   "confirmed",
            "insertion_order": 60,
        }
    ], char_id="testchar")

    results = match("u1", "totally unrelated message", char_id="testchar")
    assert results == []


def test_match_multiple_confirmed_sorted_by_insertion_order(sandbox):
    from core.relationship_facts import save, match

    save("u1", [
        {"keywords": ["bbb"], "content": "B content", "enabled": True, "status": "confirmed", "insertion_order": 80},
        {"keywords": ["aaa"], "content": "A content", "enabled": True, "status": "confirmed", "insertion_order": 40},
    ], char_id="testchar")

    results = match("u1", "aaa bbb hello", char_id="testchar")
    assert results == ["A content", "B content"]


# ── 4. pending / archived never injected (core safety rule) ──────────────────

def test_pending_entry_never_injected(sandbox):
    from core.relationship_facts import save, match

    save("u1", [
        {
            "keywords": ["secretkw"],
            "content":  "should not appear",
            "enabled":  False,    # 实际闸门：建议器写 enabled:false
            "status":   "pending",
            "insertion_order": 60,
        }
    ], char_id="testchar")

    results = match("u1", "secretkw hello", char_id="testchar")
    assert results == [], "pending entries (enabled:false) must never be injected"


def test_archived_entry_never_injected(sandbox):
    from core.relationship_facts import save, match

    save("u1", [
        {
            "keywords": ["oldkw"],
            "content":  "archived content",
            "enabled":  False,    # archived 也关闸
            "status":   "archived",
            "insertion_order": 60,
        }
    ], char_id="testchar")

    results = match("u1", "oldkw hello", char_id="testchar")
    assert results == [], "archived entries must never be injected"


# ── 5. confirm / reject semantics ────────────────────────────────────────────

def test_confirm_makes_pending_entry_injectable(sandbox):
    from core.relationship_facts import load, save, match

    save("u1", [
        {"keywords": ["newkw"], "content": "new content",
         "enabled": False, "status": "pending", "insertion_order": 60}
    ], char_id="testchar")

    # simulate confirm: set enabled:true + status:confirmed
    facts = load("u1", char_id="testchar")
    facts[0]["enabled"] = True
    facts[0]["status"] = "confirmed"
    save("u1", facts, char_id="testchar")

    results = match("u1", "newkw here", char_id="testchar")
    assert len(results) == 1
    assert results[0] == "new content"


def test_reject_archives_and_stops_injection(sandbox):
    from core.relationship_facts import load, save, match

    save("u1", [
        {"keywords": ["removekw"], "content": "removable content",
         "enabled": True, "status": "confirmed", "insertion_order": 60}
    ], char_id="testchar")

    # simulate reject: enabled:false + status:archived
    facts = load("u1", char_id="testchar")
    facts[0]["enabled"] = False
    facts[0]["status"] = "archived"
    save("u1", facts, char_id="testchar")

    results = match("u1", "removekw here", char_id="testchar")
    assert results == []

    # entry still exists for audit trail
    remaining = load("u1", char_id="testchar")
    assert remaining[0]["status"] == "archived"


# ── 6. address suggester ─────────────────────────────────────────────────────

def test_suggester_produces_pending_with_source(sandbox):
    from core.relationship_facts import load, run_address_suggester

    # "师傅" (master/teacher) used as sentence-initial address across 20 days
    today = datetime.date.today()
    for i in range(20):
        d_str = (today - datetime.timedelta(days=i)).isoformat()
        _write_event_log(sandbox, "u2", "testchar", d_str,
                         [f"师傅，第{i}天了"])

    new_facts = run_address_suggester(
        "u2", "testchar",
        days=20,
        freq_threshold=5,
        min_start_count=3,
    )

    assert len(new_facts) >= 1
    terms = [f["keywords"][0] for f in new_facts]
    assert "师傅" in terms

    fact = next(f for f in new_facts if f["keywords"][0] == "师傅")
    assert fact["status"] == "pending"
    assert "event_log" in fact["source"]
    assert "师傅" in fact["source"]


def test_suggester_all_pending(sandbox):
    from core.relationship_facts import load, run_address_suggester

    today = datetime.date.today()
    for i in range(15):
        d_str = (today - datetime.timedelta(days=i)).isoformat()
        _write_event_log(sandbox, "u5", "testchar", d_str,
                         [f"老师，第{i}天"])

    run_address_suggester("u5", "testchar", days=15, freq_threshold=5, min_start_count=3)

    facts = load("u5", char_id="testchar")
    # all generated entries must be pending
    assert all(f["status"] == "pending" for f in facts), \
        "suggester must only produce pending entries"
    assert all(f.get("enabled") == False for f in facts), \
        "suggester must write enabled:false so pending entries never inject"


def test_suggester_does_not_duplicate_existing(sandbox):
    from core.relationship_facts import load, save, run_address_suggester

    # pre-populate with a confirmed entry for "小鬼"
    save("u4", [
        {"keywords": ["小鬼"], "content": "existing", "enabled": True, "status": "confirmed", "insertion_order": 60}
    ], char_id="testchar")

    today = datetime.date.today()
    for i in range(10):
        d_str = (today - datetime.timedelta(days=i)).isoformat()
        _write_event_log(sandbox, "u4", "testchar", d_str,
                         [f"小鬼，第{i}天"])

    run_address_suggester("u4", "testchar", days=10, freq_threshold=3, min_start_count=3)

    facts = load("u4", char_id="testchar")
    kw1_entries = [f for f in facts if "小鬼" in (f.get("keywords") or [])]
    assert len(kw1_entries) == 1, "should not create duplicate pending for already-known keyword"


def test_suggester_returns_empty_when_no_log_dir(sandbox):
    from core.relationship_facts import run_address_suggester

    result = run_address_suggester("u_nodata", "testchar", days=30)
    assert result == []


# ── 7. multi-user isolation ──────────────────────────────────────────────────

def test_user_isolation(sandbox):
    from core.relationship_facts import save, match

    save("alice", [
        {"keywords": ["alicekw"], "content": "alice content", "enabled": True, "status": "confirmed", "insertion_order": 60}
    ], char_id="testchar")
    save("bob", [
        {"keywords": ["bobkw"], "content": "bob content", "enabled": True, "status": "confirmed", "insertion_order": 60}
    ], char_id="testchar")

    alice_result = match("alice", "alicekw appears", char_id="testchar")
    bob_sees_alice = match("bob", "alicekw appears", char_id="testchar")

    assert alice_result == ["alice content"]
    assert bob_sees_alice == [], "bob must not see alice's relationship facts"
