"""
tests/test_user_hidden_state_integrator.py
==========================================
Phase 1 MVP — integrator unit tests

Verification checklist:
  1. No envelope (WriteEnvelope() default) → rejected
  2. can_write_memory=False → rejected
  3. SEEK_COMPANIONSHIP → touch_need.deficit decreases
  4. NO_INTERACTION → touch_need.deficit increases
  5. RECEIVED_COMFORT → touch_need.deficit decreases
  6. impression (valid weight) → sensitivity.current increases
  7. Long-term fields unchanged after all event types + impression
"""
import pytest

from core.memory.user_hidden_state import (
    DREAM_GATE_MAX,
    DREAM_GATE_MIN,
    ImpressionInput,
    default_hidden_state,
)
from core.memory.user_hidden_state_integrator import (
    IntegratorResult,
    RealityEventType,
    integrate_event,
    integrate_impression,
)
from core.write_envelope import WriteEnvelope, stamp_user_chat

NOW = "2026-06-02T00:00:00Z"


def _open_envelope() -> WriteEnvelope:
    return stamp_user_chat()


def _snapshot_long_term(state):
    """Return a tuple of all long-term field values for comparison."""
    return (
        state.sensitivity.baseline.value,
        state.touch_need.baseline.value,
        state.embodied_ease.value,
        list(state.body_memory.entries),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 1. No envelope (WriteEnvelope() default) → rejected
# ═══════════════════════════════════════════════════════════════════════════════

class TestNoEnvelope:
    def test_seek_companionship_no_envelope_rejected(self):
        state = default_hidden_state()
        envelope = WriteEnvelope()  # zero-value, fail-closed
        _, result = integrate_event(
            RealityEventType.SEEK_COMPANIONSHIP, state, envelope, NOW
        )
        assert result.rejected
        assert not result.accepted
        assert result.rejected_reasons

    def test_impression_no_envelope_rejected(self):
        state = default_hidden_state()
        envelope = WriteEnvelope()
        imp = ImpressionInput(weight=(DREAM_GATE_MIN + DREAM_GATE_MAX) / 2)
        _, result = integrate_impression(imp, state, envelope, NOW)
        assert result.rejected
        assert not result.accepted


# ═══════════════════════════════════════════════════════════════════════════════
# 2. can_write_memory=False → rejected
# ═══════════════════════════════════════════════════════════════════════════════

class TestCanWriteMemoryFalse:
    def test_event_can_write_false_rejected(self):
        state = default_hidden_state()
        envelope = WriteEnvelope(can_write_memory=False)
        _, result = integrate_event(
            RealityEventType.RECEIVED_COMFORT, state, envelope, NOW
        )
        assert result.rejected
        assert len(result.rejected_reasons) == 1
        assert "can_write_memory=False" in result.rejected_reasons[0]

    def test_impression_can_write_false_rejected(self):
        state = default_hidden_state()
        envelope = WriteEnvelope(can_write_memory=False)
        imp = ImpressionInput(weight=DREAM_GATE_MIN)
        _, result = integrate_impression(imp, state, envelope, NOW)
        assert result.rejected

    def test_state_unchanged_when_rejected(self):
        state = default_hidden_state()
        original_deficit = state.touch_need.deficit.value
        envelope = WriteEnvelope(can_write_memory=False)
        state, result = integrate_event(
            RealityEventType.NO_INTERACTION, state, envelope, NOW
        )
        assert state.touch_need.deficit.value == original_deficit
        assert result.rejected


# ═══════════════════════════════════════════════════════════════════════════════
# 3. SEEK_COMPANIONSHIP → touch_need.deficit decreases
# ═══════════════════════════════════════════════════════════════════════════════

class TestSeekCompanionship:
    def test_deficit_decreases(self):
        state = default_hidden_state()
        state.touch_need.deficit.value = 40.0
        envelope = _open_envelope()
        state, result = integrate_event(
            RealityEventType.SEEK_COMPANIONSHIP, state, envelope, NOW
        )
        assert result.accepted
        assert state.touch_need.deficit.value < 40.0

    def test_deficit_not_below_zero(self):
        state = default_hidden_state()
        state.touch_need.deficit.value = 2.0
        envelope = _open_envelope()
        state, _ = integrate_event(
            RealityEventType.SEEK_COMPANIONSHIP, state, envelope, NOW
        )
        assert state.touch_need.deficit.value >= 0.0

    def test_result_contains_field_delta(self):
        state = default_hidden_state()
        state.touch_need.deficit.value = 50.0
        envelope = _open_envelope()
        state, result = integrate_event(
            RealityEventType.SEEK_COMPANIONSHIP, state, envelope, NOW
        )
        assert len(result.touched_fields) == 1
        delta = result.touched_fields[0]
        assert delta.field == "touch_need.deficit"
        assert delta.old_value == 50.0
        assert delta.new_value < 50.0


# ═══════════════════════════════════════════════════════════════════════════════
# 4. NO_INTERACTION → touch_need.deficit increases
# ═══════════════════════════════════════════════════════════════════════════════

class TestNoInteraction:
    def test_deficit_increases(self):
        state = default_hidden_state()
        state.touch_need.deficit.value = 20.0
        envelope = _open_envelope()
        state, result = integrate_event(
            RealityEventType.NO_INTERACTION, state, envelope, NOW
        )
        assert result.accepted
        assert state.touch_need.deficit.value > 20.0

    def test_deficit_not_above_max(self):
        state = default_hidden_state()
        state.touch_need.deficit.value = 98.0
        envelope = _open_envelope()
        state, _ = integrate_event(
            RealityEventType.NO_INTERACTION, state, envelope, NOW
        )
        assert state.touch_need.deficit.value <= 100.0

    def test_result_contains_field_delta(self):
        state = default_hidden_state()
        state.touch_need.deficit.value = 30.0
        envelope = _open_envelope()
        state, result = integrate_event(
            RealityEventType.NO_INTERACTION, state, envelope, NOW
        )
        delta = result.touched_fields[0]
        assert delta.field == "touch_need.deficit"
        assert delta.new_value > delta.old_value


# ═══════════════════════════════════════════════════════════════════════════════
# 5. RECEIVED_COMFORT → touch_need.deficit decreases
# ═══════════════════════════════════════════════════════════════════════════════

class TestReceivedComfort:
    def test_deficit_decreases(self):
        state = default_hidden_state()
        state.touch_need.deficit.value = 60.0
        envelope = _open_envelope()
        state, result = integrate_event(
            RealityEventType.RECEIVED_COMFORT, state, envelope, NOW
        )
        assert result.accepted
        assert state.touch_need.deficit.value < 60.0

    def test_result_source_matches_event(self):
        state = default_hidden_state()
        state.touch_need.deficit.value = 60.0
        envelope = _open_envelope()
        _, result = integrate_event(
            RealityEventType.RECEIVED_COMFORT, state, envelope, NOW
        )
        assert result.source == RealityEventType.RECEIVED_COMFORT.value


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Impression → sensitivity.current increases
# ═══════════════════════════════════════════════════════════════════════════════

class TestImpressionIntegration:
    def test_sensitivity_current_increases(self):
        state = default_hidden_state()
        original = state.sensitivity.current.value
        envelope = _open_envelope()
        mid_weight = (DREAM_GATE_MIN + DREAM_GATE_MAX) / 2
        imp = ImpressionInput(weight=mid_weight)
        state, result = integrate_impression(imp, state, envelope, NOW)
        assert result.accepted
        assert state.sensitivity.current.value > original

    def test_sensitivity_not_above_max(self):
        state = default_hidden_state()
        state.sensitivity.current.value = 99.0
        envelope = _open_envelope()
        imp = ImpressionInput(weight=DREAM_GATE_MAX)
        state, _ = integrate_impression(imp, state, envelope, NOW)
        assert state.sensitivity.current.value <= 100.0

    def test_weight_below_min_rejected(self):
        state = default_hidden_state()
        envelope = _open_envelope()
        imp = ImpressionInput(weight=DREAM_GATE_MIN - 0.01)
        _, result = integrate_impression(imp, state, envelope, NOW)
        assert result.rejected
        assert "gate" in result.rejected_reasons[0]

    def test_weight_above_max_rejected(self):
        state = default_hidden_state()
        envelope = _open_envelope()
        imp = ImpressionInput(weight=DREAM_GATE_MAX + 0.01)
        _, result = integrate_impression(imp, state, envelope, NOW)
        assert result.rejected

    def test_result_contains_field_delta(self):
        state = default_hidden_state()
        state.sensitivity.current.value = 50.0
        envelope = _open_envelope()
        imp = ImpressionInput(weight=DREAM_GATE_MAX)
        state, result = integrate_impression(imp, state, envelope, NOW)
        assert len(result.touched_fields) == 1
        delta = result.touched_fields[0]
        assert delta.field == "sensitivity.current"
        assert delta.new_value > delta.old_value


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Long-term fields unchanged after all operations
# ═══════════════════════════════════════════════════════════════════════════════

class TestLongTermFieldsProtected:
    def _run_all_events(self, state, envelope):
        for event in RealityEventType:
            state, _ = integrate_event(event, state, envelope, NOW)
        imp = ImpressionInput(weight=(DREAM_GATE_MIN + DREAM_GATE_MAX) / 2)
        state, _ = integrate_impression(imp, state, envelope, NOW)
        return state

    def test_sensitivity_baseline_unchanged(self):
        state = default_hidden_state()
        original = state.sensitivity.baseline.value
        envelope = _open_envelope()
        state = self._run_all_events(state, envelope)
        assert state.sensitivity.baseline.value == original

    def test_touch_need_baseline_unchanged(self):
        state = default_hidden_state()
        original = state.touch_need.baseline.value
        envelope = _open_envelope()
        state = self._run_all_events(state, envelope)
        assert state.touch_need.baseline.value == original

    def test_embodied_ease_unchanged(self):
        state = default_hidden_state()
        original = state.embodied_ease.value
        envelope = _open_envelope()
        state = self._run_all_events(state, envelope)
        assert state.embodied_ease.value == original

    def test_body_memory_unchanged(self):
        state = default_hidden_state()
        original_entries = list(state.body_memory.entries)
        envelope = _open_envelope()
        state = self._run_all_events(state, envelope)
        assert list(state.body_memory.entries) == original_entries

    def test_sensitivity_current_not_touched_by_event(self):
        """Reality events must not change sensitivity.current."""
        state = default_hidden_state()
        original = state.sensitivity.current.value
        envelope = _open_envelope()
        for event in (
            RealityEventType.SEEK_COMPANIONSHIP,
            RealityEventType.RECEIVED_COMFORT,
            RealityEventType.NO_INTERACTION,
        ):
            s2 = default_hidden_state()
            s2.sensitivity.current.value = original
            s2, _ = integrate_event(event, s2, envelope, NOW)
            assert s2.sensitivity.current.value == original, (
                f"event {event.value} must not touch sensitivity.current"
            )

    def test_touch_deficit_not_touched_by_impression(self):
        """Impression must not change touch_need.deficit."""
        state = default_hidden_state()
        state.touch_need.deficit.value = 30.0
        envelope = _open_envelope()
        imp = ImpressionInput(weight=(DREAM_GATE_MIN + DREAM_GATE_MAX) / 2)
        state, _ = integrate_impression(imp, state, envelope, NOW)
        assert state.touch_need.deficit.value == 30.0
