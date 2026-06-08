"""
ScenarioCore — isolated kernel for Scenario-mode dreams.

Shared envelope (dream_state): carries status, dream_id, context_snapshot, etc.
Isolated kernel: ScenarioCore carries only script-progression state.

Explicitly NOT connected to:
- user_hidden_state / symbolic_anchors
- dream_depth / dream_stability (Mirror HUD fields)
- impression write-back
- afterglow long-term integration

Stored as dream_state["scenario_core"] (nested dict, cleared by clear_local_state).

Progress signal fields (v0.6 — observation skeleton):
- last_progress_signal: "not_close" | "approaching" | "satisfied" | None
- last_matched_exit_signs: list[str]  — current-stage exit_signs referenced by LLM
- last_blocked_events: list[str]      — not_yet_allowed items attempted by user

Stage transition fields (v0.7 — sequential advance):
- satisfied_streak: int  — consecutive turns where progress_signal == "satisfied"
  Resets to 0 on non-satisfied signal, on missing/invalid control block (conservative),
  and on stage advance. When >= 2, triggers advance to next stage.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

VALID_PROGRESS_SIGNALS: frozenset[str] = frozenset({"not_close", "approaching", "satisfied"})


@dataclass(frozen=True)
class ScenarioCore:
    script_id: str
    current_stage_id: str
    stage_turns: int = 0
    ending_state: str | None = None
    last_progress_signal: str | None = None
    last_matched_exit_signs: list[str] = field(default_factory=list)
    last_blocked_events: list[str] = field(default_factory=list)
    satisfied_streak: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "script_id": self.script_id,
            "current_stage_id": self.current_stage_id,
            "stage_turns": self.stage_turns,
            "ending_state": self.ending_state,
            "last_progress_signal": self.last_progress_signal,
            "last_matched_exit_signs": list(self.last_matched_exit_signs),
            "last_blocked_events": list(self.last_blocked_events),
            "satisfied_streak": self.satisfied_streak,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ScenarioCore":
        return cls(
            script_id=str(data["script_id"]),
            current_stage_id=str(data["current_stage_id"]),
            stage_turns=int(data.get("stage_turns", 0)),
            ending_state=data.get("ending_state"),
            last_progress_signal=data.get("last_progress_signal"),
            last_matched_exit_signs=list(data.get("last_matched_exit_signs") or []),
            last_blocked_events=list(data.get("last_blocked_events") or []),
            satisfied_streak=int(data.get("satisfied_streak", 0)),
        )

    def increment_stage_turns(self) -> "ScenarioCore":
        """Return a new ScenarioCore with stage_turns incremented by 1 (frozen dataclass)."""
        return replace(self, stage_turns=self.stage_turns + 1)

    def with_progress_signal(
        self,
        signal: str,
        matched_exit_signs: list[str] | None = None,
        blocked_events: list[str] | None = None,
    ) -> "ScenarioCore":
        """Return a new ScenarioCore with progress signal fields updated (frozen dataclass).

        satisfied_streak increments only on "satisfied"; resets to 0 on any other signal.
        """
        new_streak = (self.satisfied_streak + 1) if signal == "satisfied" else 0
        return replace(
            self,
            last_progress_signal=signal,
            last_matched_exit_signs=list(matched_exit_signs or []),
            last_blocked_events=list(blocked_events or []),
            satisfied_streak=new_streak,
        )

    def reset_satisfied_streak(self) -> "ScenarioCore":
        """Return new ScenarioCore with satisfied_streak reset to 0.

        Called when control block is absent or invalid — conservative choice to prevent
        silent stage promotion when the LLM occasionally omits the control block.
        """
        return replace(self, satisfied_streak=0)

    def advance_to_stage(self, next_stage_id: str) -> "ScenarioCore":
        """Advance to next_stage_id, resetting all per-stage progression state.

        ending_state is intentionally preserved (unchanged) — caller sets it separately
        when needed (e.g. mark_completed on last stage).
        """
        return replace(
            self,
            current_stage_id=next_stage_id,
            stage_turns=0,
            last_progress_signal=None,
            last_matched_exit_signs=[],
            last_blocked_events=[],
            satisfied_streak=0,
        )

    def mark_completed(self) -> "ScenarioCore":
        """Mark scenario as completed (final stage satisfied streak reached)."""
        return replace(self, ending_state="completed")

    @classmethod
    def from_script(cls, script: dict[str, Any]) -> "ScenarioCore":
        """Create a fresh ScenarioCore from a loaded script, starting at stage[0]."""
        stages = script.get("stages") or []
        if not stages:
            raise ValueError(f"script {script.get('id')!r} has no stages")
        return cls(
            script_id=str(script["id"]),
            current_stage_id=str(stages[0]["id"]),
            stage_turns=0,
            ending_state=None,
        )
