"""
presence_model.py — raw sensor signal → attributed PresenceState

Translates idle_seconds / timestamps into a semantic PresenceState so that
prompt consumers receive attributed context instead of bare minute-counts.

Pure functions only — no I/O, no LLM calls, no side effects.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

from core.scheduler.rhythm import is_quiet_sleep_time


class PhysicalPresence(str, Enum):
    PRESENT = "present"   # idle < 60s
    IDLE    = "idle"      # 60s <= idle < 300s
    AWAY    = "away"      # idle >= 300s


class Attribution(str, Enum):
    ACTIVE_CHATTING  = "ACTIVE_CHATTING"   # gap < 2 min
    FOCUSED_SILENT   = "FOCUSED_SILENT"    # present + long gap (focused, not ignoring)
    PRESENT_IDLE     = "PRESENT_IDLE"      # present or briefly idle, gap < 30 min
    BRIEFLY_AWAY     = "BRIEFLY_AWAY"      # away < 30 min
    GENUINELY_ABSENT = "GENUINELY_ABSENT"  # away >= 30 min
    SLEEPING         = "SLEEPING"          # sleep window + idle >= 300s


@dataclass(frozen=True)
class PresenceState:
    physical:               PhysicalPresence
    attribution:            Attribution
    conversational_gap_min: Optional[int]  # None = no chat this session
    proactive_gap_min:      Optional[int]
    at_desk_min:            int
    is_sleep_window:        bool
    state_summary:          str            # pre-rendered; "" for SLEEPING


def _render_summary(attribution: Attribution, at_desk_min: int) -> str:
    if attribution == Attribution.SLEEPING:
        return ""
    if attribution == Attribution.ACTIVE_CHATTING:
        return "刚刚还在交流"
    if attribution == Attribution.FOCUSED_SILENT:
        if at_desk_min >= 120:
            return "她在桌前专注做事，已经好一会儿了"
        return "她在桌前专注做事"
    if attribution == Attribution.PRESENT_IDLE:
        return "她还在，只是暂时没动"
    if attribution == Attribution.BRIEFLY_AWAY:
        return "她刚走开一会儿"
    if attribution == Attribution.GENUINELY_ABSENT:
        return "她离开有一阵了"
    return ""


def derive_presence_state(
    *,
    idle_seconds: float | int,
    continuous_at_desk_seconds: float | int,
    last_chat_at: Optional[float],
    last_proactive_at: Optional[float],
    now: Optional[float] = None,
    away_since: Optional[float] = None,
) -> PresenceState:
    """
    Derive a PresenceState from raw sensor signals.

    Parameters
    ----------
    idle_seconds               seconds since last keyboard/mouse activity
    continuous_at_desk_seconds seconds the current desk session has been active
    last_chat_at               unix ts of last user message, or None
    last_proactive_at          unix ts of last proactive message, or None
    now                        unix ts for "now" (default: time.time())
    away_since                 unix ts when physical absence began, or None
                               (None → conservative; away_duration treated as 0)
    """
    ts_now   = float(now if now is not None else time.time())
    local_dt = datetime.fromtimestamp(ts_now)
    sleep_win = is_quiet_sleep_time(local_dt)

    idle_s      = float(idle_seconds)
    at_desk_min = int(float(continuous_at_desk_seconds) / 60)

    conversational_gap_min: Optional[int]
    if last_chat_at is None:
        conversational_gap_min = None
    else:
        conversational_gap_min = int((ts_now - float(last_chat_at)) / 60)

    proactive_gap_min: Optional[int]
    if last_proactive_at is None:
        proactive_gap_min = None
    else:
        proactive_gap_min = int((ts_now - float(last_proactive_at)) / 60)

    # Physical presence tier
    if idle_s < 60:
        physical = PhysicalPresence.PRESENT
    elif idle_s < 300:
        physical = PhysicalPresence.IDLE
    else:
        physical = PhysicalPresence.AWAY

    # Conservative: if away_since unknown, treat away_duration as 0 to avoid
    # misclassifying a fresh departure as GENUINELY_ABSENT.
    away_duration_min = (
        int((ts_now - float(away_since)) / 60) if away_since is not None else 0
    )

    # Attribution: first match wins
    if sleep_win and idle_s >= 300:
        # Sleep guard overrides everything — never interpret absence as ignoring
        attribution = Attribution.SLEEPING

    elif conversational_gap_min is None or conversational_gap_min < 2:
        attribution = Attribution.ACTIVE_CHATTING

    elif physical == PhysicalPresence.PRESENT and conversational_gap_min >= 30:
        # Physically active but long conversational gap → focused, not cold
        attribution = Attribution.FOCUSED_SILENT

    elif physical == PhysicalPresence.PRESENT:
        attribution = Attribution.PRESENT_IDLE

    elif physical == PhysicalPresence.IDLE:
        # Brief keyboard pause, still at desk
        attribution = Attribution.PRESENT_IDLE

    elif away_duration_min < 30:
        attribution = Attribution.BRIEFLY_AWAY

    else:
        attribution = Attribution.GENUINELY_ABSENT

    return PresenceState(
        physical=physical,
        attribution=attribution,
        conversational_gap_min=conversational_gap_min,
        proactive_gap_min=proactive_gap_min,
        at_desk_min=at_desk_min,
        is_sleep_window=sleep_win,
        state_summary=_render_summary(attribution, at_desk_min),
    )
