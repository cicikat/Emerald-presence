"""
tests/memeval/test_memeval.py — pytest 收集入口（Brief 44）

`pytest tests/memeval` 全绿（xfail 除外）。单独跑见 tests/run_memeval.py。
"""

from collections import Counter

import pytest

from tests.memeval import engine

_CASES = engine.load_cases()
_RECALL_MODES = ["natural", "sem_zeroed"]


def _param_for(case: dict):
    marks = []
    if case.get("xfail"):
        marks.append(pytest.mark.xfail(reason=case["xfail_reason"], strict=True))
    return pytest.param(case, id=case["id"], marks=marks)


@pytest.mark.parametrize("recall_mode", _RECALL_MODES)
@pytest.mark.parametrize("case", [_param_for(c) for c in _CASES])
def test_memeval_case(case, recall_mode, case_env, monkeypatch):
    result = engine.run_case(case, monkeypatch, recall_mode=recall_mode, char_id=case_env)
    problems = engine.check_expectations(case, result)
    assert not problems, "\n".join(problems)


def test_case_files_cover_all_categories():
    cats = {c["category"] for c in _CASES}
    missing = engine._VALID_CATEGORIES - cats
    assert not missing, f"缺少类别覆盖: {missing}"


def test_each_category_has_minimum_cases():
    counts = Counter(c["category"] for c in _CASES)
    thin = {cat: counts.get(cat, 0) for cat in engine._VALID_CATEGORIES if counts.get(cat, 0) < 5}
    assert not thin, f"以下类别用例数 < 5: {thin}"
