"""CC 任务 19 · A4 — 失败退避（attempt-cooldown）单测。

覆盖 _record_attempt_failure 的首次 15min / 指数翻倍 / 封顶该触发器自身冷却，
以及 _is_ready() 同时读正式冷却和 attempt-cooldown 两条闸。
"""

import time

import pytest


@pytest.fixture(autouse=True)
def _isolated_backoff_state(monkeypatch):
    """隔离 loop.py 的模块级冷却/退避字典，避免跨测试污染。"""
    from core.scheduler import loop

    monkeypatch.setattr(loop, "_last_trigger", {})
    monkeypatch.setattr(loop, "_attempt_backoff_secs", {})
    monkeypatch.setattr(loop, "_attempt_cooldown_until", {})
    return loop


def test_first_failure_backs_off_15_minutes(_isolated_backoff_state, monkeypatch):
    loop = _isolated_backoff_state
    now = 1_000_000.0
    monkeypatch.setattr(time, "time", lambda: now)

    loop._record_attempt_failure("random_message")

    assert loop._attempt_cooldown_until["random_message"] == pytest.approx(now + 15 * 60)


def test_second_failure_doubles_backoff(_isolated_backoff_state, monkeypatch):
    loop = _isolated_backoff_state
    now = 1_000_000.0
    monkeypatch.setattr(time, "time", lambda: now)

    loop._record_attempt_failure("random_message")
    loop._record_attempt_failure("random_message")

    assert loop._attempt_backoff_secs["random_message"] == pytest.approx(30 * 60)
    assert loop._attempt_cooldown_until["random_message"] == pytest.approx(now + 30 * 60)


def test_backoff_caps_at_trigger_own_cooldown(_isolated_backoff_state, monkeypatch):
    loop = _isolated_backoff_state
    now = 1_000_000.0
    monkeypatch.setattr(time, "time", lambda: now)

    # night_reminder cooldown is 5h = 18000s; repeated failures should never exceed it.
    for _ in range(10):
        loop._record_attempt_failure("night_reminder")

    cap = loop._COOLDOWNS["night_reminder"]
    assert loop._attempt_backoff_secs["night_reminder"] == cap


def test_clear_attempt_backoff_resets_state(_isolated_backoff_state):
    loop = _isolated_backoff_state
    loop._record_attempt_failure("random_message")
    assert not loop._attempt_cooldown_ready("random_message")

    loop._clear_attempt_backoff("random_message")

    assert loop._attempt_cooldown_ready("random_message")
    assert "random_message" not in loop._attempt_backoff_secs


def test_failure_then_success_then_failure_restarts_at_15_minutes(_isolated_backoff_state, monkeypatch):
    loop = _isolated_backoff_state
    now = 1_000_000.0
    monkeypatch.setattr(time, "time", lambda: now)

    loop._record_attempt_failure("random_message")
    loop._record_attempt_failure("random_message")  # now at 30min backoff
    loop._clear_attempt_backoff("random_message")   # success clears it

    loop._record_attempt_failure("random_message")  # next failure restarts at 15min
    assert loop._attempt_backoff_secs["random_message"] == pytest.approx(15 * 60)


def test_is_ready_checks_both_cooldown_and_attempt_backoff(_isolated_backoff_state, monkeypatch):
    loop = _isolated_backoff_state
    now = 1_000_000.0
    monkeypatch.setattr(time, "time", lambda: now)

    # Regular cooldown elapsed (never triggered), but attempt-backoff active.
    loop._record_attempt_failure("random_message")
    assert loop._is_ready("random_message") is False

    # Advance past the attempt-backoff window.
    monkeypatch.setattr(time, "time", lambda: now + 15 * 60 + 1)
    assert loop._is_ready("random_message") is True


def test_is_ready_still_respects_regular_cooldown_independent_of_backoff(_isolated_backoff_state, monkeypatch):
    loop = _isolated_backoff_state
    now = 1_000_000.0
    monkeypatch.setattr(time, "time", lambda: now)

    # Trigger just fired successfully (regular cooldown active); no attempt-backoff.
    loop._mark("random_message")
    assert loop._is_ready("random_message") is False
