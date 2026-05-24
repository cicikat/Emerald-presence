from datetime import datetime

import pytest

from core.sandbox import safe_user_id


def test_datapaths_rejects_parent_traversal(sandbox):
    with pytest.raises(ValueError):
        sandbox._p("../evil")


def test_datapaths_rejects_absolute_part(sandbox, tmp_path):
    with pytest.raises(ValueError):
        sandbox._p(tmp_path / "evil")


def test_datapaths_fixed_paths_still_generate(sandbox, tmp_path):
    assert sandbox.history() == tmp_path / "history"
    assert sandbox.channel_queue() == tmp_path / "channel_queue.json"


def test_safe_user_id_digits_unchanged():
    assert safe_user_id("1043484516") == "1043484516"


def test_memory_paths_reject_malicious_uid(sandbox):
    from core.memory import episodic_memory, event_log, mid_term, short_term, user_identity, user_profile

    checks = [
        lambda: short_term._history_path("../evil"),
        lambda: user_profile._profile_path("../evil"),
        lambda: user_identity._identity_file("../evil"),
        lambda: event_log._day_file("../evil", datetime(2026, 1, 1)),
        lambda: event_log._full_log_file("../evil"),
        lambda: episodic_memory._mem_file("../evil"),
        lambda: episodic_memory._index_file("../evil"),
        lambda: mid_term._file("../evil"),
    ]

    for check in checks:
        with pytest.raises(ValueError):
            check()
