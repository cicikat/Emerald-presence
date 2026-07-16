"""
Tests for get_mood_text() — verifies thinking/sleepy have dedicated copy
and do not fall back to neutral wording, plus previous/pending 混合文案。
"""

import time

import pytest
from core.config_loader import _char_name
from core.mood_text import MOOD_TEXT, PENDING_SUFFIX, RESIDUAL_TEXT, get_mood_text

_NEUTRAL_TEXTS = set(MOOD_TEXT["neutral"])


@pytest.mark.parametrize("emotion", ["thinking", "sleepy"])
def test_emotion_has_own_entry(emotion):
    assert emotion in MOOD_TEXT, f"{emotion} missing from MOOD_TEXT"


@pytest.mark.parametrize("emotion,intensity", [
    ("thinking", 0.2),
    ("thinking", 0.5),
    ("thinking", 0.8),
    ("sleepy",   0.2),
    ("sleepy",   0.5),
    ("sleepy",   0.8),
])
def test_not_neutral_fallback(emotion, intensity):
    state = {"current": emotion, "intensity": intensity}
    text = get_mood_text(state)
    for neutral_phrase in _NEUTRAL_TEXTS:
        assert neutral_phrase not in text, (
            f"get_mood_text({emotion!r}, intensity={intensity}) returned neutral copy: {text!r}"
        )


def test_residual_within_window():
    state = {
        "current": "gentle",
        "intensity": 0.5,
        "previous": "sad",
        "pending": None,
        "updated_at": time.time() - 600,  # 10 分钟前
    }
    text = get_mood_text(state)
    assert RESIDUAL_TEXT["sad"] in text


def test_residual_outside_window():
    state = {
        "current": "gentle",
        "intensity": 0.5,
        "previous": "sad",
        "pending": None,
        "updated_at": time.time() - 3600,  # 1 小时前，超出 30 分钟窗口
    }
    text = get_mood_text(state)
    assert RESIDUAL_TEXT["sad"] not in text


@pytest.mark.parametrize("previous", ["neutral", "gentle"])
def test_no_residual_when_previous_neutral_or_same(previous):
    # previous="gentle" 与 current 相同、或 previous="neutral"，都应与现状一致（无残留句）
    state = {
        "current": "gentle",
        "intensity": 0.5,
        "previous": previous,
        "pending": None,
        "updated_at": time.time() - 60,
    }
    text = get_mood_text(state)
    assert text == f"{_char_name()}此刻：平静，带一点轻盈。"


def test_pending_wins_over_residual():
    state = {
        "current": "gentle",
        "intensity": 0.5,
        "previous": "sad",
        "pending": "happy",
        "updated_at": time.time() - 60,
    }
    text = get_mood_text(state)
    assert PENDING_SUFFIX in text
    assert RESIDUAL_TEXT["sad"] not in text


def test_yandere_current_no_residual():
    state = {
        "current": "yandere",
        "intensity": 0.9,
        "previous": "sad",
        "pending": None,
        "updated_at": time.time() - 60,
    }
    text = get_mood_text(state)
    assert RESIDUAL_TEXT["sad"] not in text


def test_regression_missing_previous_and_updated_at():
    # 旧调用点仍可能不传 previous/updated_at，应与改动前行为一致
    state = {"current": "happy", "intensity": 0.5}
    text = get_mood_text(state)
    assert text == f"{_char_name()}此刻：心情不错。"
