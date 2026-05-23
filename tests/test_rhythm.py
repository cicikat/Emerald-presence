from datetime import datetime, date


def test_logical_day_before_cutoff_returns_previous_day():
    from core.scheduler.rhythm import logical_day

    assert logical_day(datetime(2026, 5, 24, 2, 0)) == date(2026, 5, 23)


def test_logical_day_after_cutoff_returns_current_day():
    from core.scheduler.rhythm import logical_day

    assert logical_day(datetime(2026, 5, 23, 23, 0)) == date(2026, 5, 23)
