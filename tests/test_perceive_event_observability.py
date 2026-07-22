"""C2 coverage for explicit trust and read-only stimulus audit discovery."""

import asyncio
import json
from types import SimpleNamespace

import pytest

from core.perceive_event import PerceiveEvent


def test_perceive_event_derives_trust_and_allows_explicit_override():
    defaulted = PerceiveEvent(source="scheduler", uid="u1", channel="system", kind="scheduled")
    overridden = PerceiveEvent(
        source="scheduler",
        uid="u1",
        channel="system",
        kind="scheduled",
        trust="high_trust",
    )

    assert defaulted.trust == "low_trust"
    assert overridden.trust == "high_trust"
    with pytest.raises(ValueError, match="invalid PerceiveEvent trust"):
        PerceiveEvent(source="scheduler", uid="u1", channel="system", kind="scheduled", trust="unknown")


def test_perceive_event_audit_filters_and_paginates(tmp_path, monkeypatch):
    from core import perceive_event_audit

    audit_root = tmp_path / "event_log"
    user_one = audit_root / "u1"
    user_two = audit_root / "u2"
    user_one.mkdir(parents=True)
    user_two.mkdir()
    (user_one / "trigger_audit.jsonl").write_text(
        "\n".join(
            json.dumps(record)
            for record in (
                {"ts": 10, "source": "scheduler", "gate_result": "accepted", "kind": "stimulus"},
                {"ts": 30, "source": "desktop_wake", "gate_result": "accepted", "kind": "stimulus"},
            )
        ) + "\n",
        encoding="utf-8",
    )
    (user_two / "trigger_audit.jsonl").write_text(
        json.dumps({"ts": 20, "source": "scheduler", "gate_result": "blocked_dream", "kind": "stimulus"}) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(perceive_event_audit, "get_paths", lambda: SimpleNamespace(_p=lambda *_: audit_root))

    entries, total = perceive_event_audit.query(source="scheduler", offset=1, limit=1)
    assert total == 2
    assert entries == [{"ts": 10, "source": "scheduler", "gate_result": "accepted", "kind": "stimulus"}]

    blocked, total = perceive_event_audit.query(gate_result="blocked_dream", offset=0, limit=10)
    assert total == 1
    assert blocked[0]["source"] == "scheduler"


def test_perceive_event_endpoint_returns_pagination_metadata(monkeypatch):
    from admin.routers import observability
    from core import perceive_event_audit

    monkeypatch.setattr(
        perceive_event_audit,
        "query",
        lambda **kwargs: ([{"event_id": "evt-1", "kind": "stimulus"}], 3),
    )

    response = asyncio.run(
        observability.perceive_events(
            source="scheduler",
            gate_result="accepted",
            offset=2,
            limit=1,
            _auth="test",
        )
    )
    assert response == {
        "entries": [{"event_id": "evt-1", "kind": "stimulus"}],
        "count": 1,
        "total": 3,
        "offset": 2,
        "limit": 1,
    }
