from core.scheduler.urgency import UrgencyTier, urgency_in_tier


def test_urgency_in_tier_maps_ratio_into_range():
    assert urgency_in_tier(UrgencyTier.MUST_NOT_MISS, 0) == 0.9
    assert urgency_in_tier(UrgencyTier.MUST_NOT_MISS, 1) == 1.0
    assert urgency_in_tier(UrgencyTier.WINDOW_EVENT, 0.5) == 0.795


def test_urgency_in_tier_clamps_ratio():
    assert urgency_in_tier(UrgencyTier.FILLER, -1) == 0.1
    assert urgency_in_tier(UrgencyTier.FILLER, 2) == 0.29


def test_urgency_in_tier_accepts_string_tier():
    assert urgency_in_tier("daily_rhythm", 0) == 0.5
