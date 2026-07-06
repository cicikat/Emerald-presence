"""
Her body state projection for the character's perception.

The character only sees what this projection renders — never raw numbers by
default. She (user/her) always sees her own numbers in the UI panel,
orthogonal to boundary_level (user_sees_own_numbers is always True on her side).

BoundaryLevel:
  vague            — single ambiguous hint; no axis breakdown
  body_perceptible — qualitative per-axis labels (no numbers) [DEFAULT]
  numbers_visible  — numeric values shown to the character
  threshold_break  — numeric + cap release (SEAM: not implemented in v0,
                     falls back to numbers_visible; full test matrix = v2)

yexuan_tension coupling (dream-local, ★ never written to reality mood_state):
  - Her heat+sensitivity → yexuan_tension increment, capped at _MAX_DELTA/turn
  - Weak signal (< 15%) → tension decays toward 0 each turn
  - yexuan_tension tops at 1.0, never below 0.0
  - Injected into D7_dream_tension in the prompt
"""

from enum import Enum
from typing import Any

from core.dream.body_state import BodyState

_YEXUAN_TENSION_MAX = 1.0
_YEXUAN_TENSION_DECAY = 0.05
_YEXUAN_TENSION_MAX_DELTA = 0.15  # hard ceiling, single-turn increment
_SIGNAL_THRESHOLD = 0.15          # below this → decay path


class BoundaryLevel(str, Enum):
    vague = "vague"
    body_perceptible = "body_perceptible"
    numbers_visible = "numbers_visible"
    threshold_break = "threshold_break"   # seam — not activated in v0


def project_body_for_yexuan(
    body: BodyState,
    boundary_level: str | BoundaryLevel = BoundaryLevel.body_perceptible,
    yexuan_tension: float = 0.0,
) -> dict[str, Any]:
    """
    Build the character's perception of her body state for this turn.

    Returns:
      {
        "d5_text":        str,    # inject into D5_body_projection
        "yexuan_tension": float,  # inject into D7_dream_tension (0.0–1.0)
      }

    ★ Output only — never writes reality mood_state or any persistent store.
    """
    if isinstance(boundary_level, str):
        try:
            level = BoundaryLevel(boundary_level)
        except ValueError:
            level = BoundaryLevel.body_perceptible
    else:
        level = boundary_level

    # yexuan_tension coupling
    signal = (body.heat + body.sensitivity) / 200.0  # normalised 0–1
    if signal < _SIGNAL_THRESHOLD:
        new_tension = max(0.0, yexuan_tension - _YEXUAN_TENSION_DECAY)
    else:
        delta = signal * (_YEXUAN_TENSION_MAX_DELTA * 2)
        delta = min(delta, _YEXUAN_TENSION_MAX_DELTA)
        new_tension = min(_YEXUAN_TENSION_MAX, yexuan_tension + delta)

    d5_text = _render_d5(body, level)

    return {
        "d5_text": d5_text,
        "yexuan_tension": round(new_tension, 4),
    }


# ── D5 renderers ─────────────────────────────────────────────────────────────

def _render_d5(body: BodyState, level: BoundaryLevel) -> str:
    if level == BoundaryLevel.vague:
        return _render_vague(body)
    elif level == BoundaryLevel.body_perceptible:
        return _render_body_perceptible(body)
    elif level in (BoundaryLevel.numbers_visible, BoundaryLevel.threshold_break):
        # threshold_break: cap release is applied in dream_pipeline via apply_threshold_break;
        # D5 rendering is the same numeric format as numbers_visible
        return _render_numbers_visible(body)
    return ""


def _render_vague(body: BodyState) -> str:
    total = (body.heat + body.sensitivity + body.tension) / 3.0
    if total < 10:
        return ""
    if total < 30:
        return "【她·感知】她似乎有些细微的变化。"
    if total < 55:
        return "【她·感知】感觉到了某种涌动，说不清楚。"
    return "【她·感知】什么东西正在悄悄漫过来，他隐约察觉到了。"


def _heat_label(v: float) -> str:
    if v < 15: return "平静"
    if v < 30: return "微热"
    if v < 50: return "温热"
    if v < 68: return "灼热"
    return "沸腾边缘"


def _sensitivity_label(v: float) -> str:
    if v < 15: return "平稳"
    if v < 30: return "轻触有感"
    if v < 50: return "敏感"
    if v < 68: return "高度敏感"
    return "过载边缘"


def _tension_label(v: float) -> str:
    if v < 15: return "放松"
    if v < 30: return "微微绷着"
    if v < 50: return "紧绷"
    if v < 72: return "强烈张力"
    return "临界"


def _render_body_perceptible(body: BodyState) -> str:
    parts: list[str] = []
    if body.heat > 8:
        parts.append(f"温度：{_heat_label(body.heat)}")
    if body.sensitivity > 8:
        parts.append(f"感知：{_sensitivity_label(body.sensitivity)}")
    if body.tension > 8:
        parts.append(f"张力：{_tension_label(body.tension)}")
    if not parts:
        return ""
    return "【她·身体读数·定性】" + "；".join(parts)


def _render_numbers_visible(body: BodyState) -> str:
    return (
        f"【她·身体读数·数值】"
        f"温度 {body.heat:.0f}／感知 {body.sensitivity:.0f}／张力 {body.tension:.0f}"
    )
