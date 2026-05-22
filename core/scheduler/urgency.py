"""
统一触发器 urgency 分档工具。

Phase 2 Step 3 起，触发器只在真实条件满足时报名，urgency 在各自档内浮动。
"""

from __future__ import annotations

from enum import Enum


class UrgencyTier(str, Enum):
    MUST_NOT_MISS = "must_not_miss"
    WINDOW_EVENT = "window_event"
    DAILY_RHYTHM = "daily_rhythm"
    REACTIVE = "reactive"
    FILLER = "filler"


URGENCY_RANGES: dict[UrgencyTier, tuple[float, float]] = {
    UrgencyTier.MUST_NOT_MISS: (0.90, 1.00),
    UrgencyTier.WINDOW_EVENT: (0.70, 0.89),
    UrgencyTier.DAILY_RHYTHM: (0.50, 0.69),
    UrgencyTier.REACTIVE: (0.30, 0.49),
    UrgencyTier.FILLER: (0.10, 0.29),
}


def urgency_in_tier(tier: UrgencyTier | str, ratio: float) -> float:
    normalized_tier = UrgencyTier(tier)
    lo, hi = URGENCY_RANGES[normalized_tier]
    clamped = min(1.0, max(0.0, float(ratio)))
    return round(lo + (hi - lo) * clamped, 3)
