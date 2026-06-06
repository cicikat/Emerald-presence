"""
tests/test_memory_resolver_remaining_paths_audit.py — P1-2J

Audit tests confirming:
1.  Core migrated stores route ALL path computation through resolve_path,
    not get_paths() / user_memory_root() / memory_char_root() for their primary file paths.
2.  character_growth is NOT in pipeline main chain
    (fetch_context / post_process / prompt_builder).
3.  consolidate_to_growth is not registered or enqueued in the slow_queue pipeline.
4.  path_resolver covers all core reality-scoped artifacts.
5.  Allowlisted non-blockers are explicitly accounted for.
6.  No new production yexuan fallback introduced in migrated stores.
"""
from __future__ import annotations

import importlib
import inspect
import sys

import pytest


# ---------------------------------------------------------------------------
# 1. Migrated stores use resolve_path for their primary file path
# ---------------------------------------------------------------------------

def test_short_term_history_path_uses_resolve_path():
    """short_term._history_path must call resolve_path, not get_paths().history()."""
    from core.memory import short_term
    src = inspect.getsource(short_term._history_path)
    assert "resolve_path" in src, "_history_path must use resolve_path"


def test_short_term_history_write_path_uses_resolve_path():
    from core.memory import short_term
    src = inspect.getsource(short_term._history_write_path)
    assert "resolve_path" in src


def test_event_log_write_dir_uses_resolve_path():
    from core.memory import event_log
    src = inspect.getsource(event_log._event_log_write_dir)
    assert "resolve_path" in src, "_event_log_write_dir must use resolve_path"


def test_event_log_read_dir_uses_resolve_path():
    from core.memory import event_log
    src = inspect.getsource(event_log._event_log_read_dir)
    assert "resolve_path" in src


def test_mid_term_read_file_uses_resolve_path():
    from core.memory import mid_term
    src = inspect.getsource(mid_term._read_file)
    assert "resolve_path" in src, "_read_file must use resolve_path"


def test_mid_term_write_file_uses_resolve_path():
    from core.memory import mid_term
    src = inspect.getsource(mid_term._write_file)
    assert "resolve_path" in src


def test_episodic_mem_read_file_uses_resolve_path():
    from core.memory import episodic_memory
    src = inspect.getsource(episodic_memory._mem_read_file)
    assert "resolve_path" in src


def test_episodic_mem_write_file_uses_resolve_path():
    from core.memory import episodic_memory
    src = inspect.getsource(episodic_memory._mem_write_file)
    assert "resolve_path" in src


def test_episodic_index_read_file_uses_resolve_path():
    from core.memory import episodic_memory
    src = inspect.getsource(episodic_memory._index_read_file)
    assert "resolve_path" in src


def test_fixation_state_read_uses_resolve_path():
    from core.memory import fixation_pipeline
    src = inspect.getsource(fixation_pipeline._state_read_file)
    assert "resolve_path" in src


def test_fixation_state_write_uses_resolve_path():
    from core.memory import fixation_pipeline
    src = inspect.getsource(fixation_pipeline._state_write_file)
    assert "resolve_path" in src


def test_user_profile_read_path_uses_resolve_path():
    from core.memory import user_profile
    src = inspect.getsource(user_profile._profile_read_path)
    assert "resolve_path" in src


def test_user_profile_write_path_uses_resolve_path():
    from core.memory import user_profile
    src = inspect.getsource(user_profile._profile_write_path)
    assert "resolve_path" in src


def test_user_identity_read_file_uses_resolve_path():
    from core.memory import user_identity
    src = inspect.getsource(user_identity._identity_read_file)
    assert "resolve_path" in src


def test_user_identity_write_file_uses_resolve_path():
    from core.memory import user_identity
    src = inspect.getsource(user_identity._identity_write_file)
    assert "resolve_path" in src


def test_hidden_state_store_load_uses_resolve_path():
    from core.memory import user_hidden_state_store
    src = inspect.getsource(user_hidden_state_store.load_hidden_state)
    assert "resolve_path" in src


def test_hidden_state_store_save_uses_resolve_path():
    from core.memory import user_hidden_state_store
    src = inspect.getsource(user_hidden_state_store.save_hidden_state)
    assert "resolve_path" in src


def test_afterglow_load_raw_uses_resolve_path():
    from core.memory import user_hidden_state_store
    src = inspect.getsource(user_hidden_state_store._load_afterglow_raw)
    assert "resolve_path" in src


# ---------------------------------------------------------------------------
# 2. character_growth NOT in pipeline main chain
# ---------------------------------------------------------------------------

def test_prompt_builder_has_no_character_growth_import():
    """prompt_builder must not import or reference character_growth module."""
    from core import prompt_builder
    src = inspect.getsource(prompt_builder)
    assert "character_growth" not in src, (
        "prompt_builder must not reference character_growth"
    )


def _has_growth_code_call(src: str) -> bool:
    """Return True if source contains actual character_growth code calls (not just comments/docstrings)."""
    import re
    # Strip docstrings (triple-quoted) and inline # comments before searching
    stripped = re.sub(r'""".*?"""', "", src, flags=re.DOTALL)
    stripped = re.sub(r"'''.*?'''", "", stripped, flags=re.DOTALL)
    stripped = re.sub(r"#[^\n]*", "", stripped)
    return ("character_growth" in stripped)


def test_pipeline_fetch_context_has_no_character_growth_call():
    """pipeline.fetch_context must not contain character_growth code calls."""
    from core import pipeline as _pipeline
    src = inspect.getsource(_pipeline.Pipeline.fetch_context)
    assert not _has_growth_code_call(src), (
        "fetch_context must not call character_growth"
    )


def test_pipeline_post_process_has_no_character_growth_call():
    """pipeline.post_process must not contain character_growth code calls."""
    from core import pipeline as _pipeline
    src = inspect.getsource(_pipeline.Pipeline.post_process)
    assert not _has_growth_code_call(src), (
        "post_process must not call character_growth"
    )


def test_pipeline_build_prompt_has_no_character_growth_call():
    """pipeline.build_prompt must not contain character_growth code calls."""
    from core import pipeline as _pipeline
    src = inspect.getsource(_pipeline.Pipeline.build_prompt)
    assert not _has_growth_code_call(src), (
        "build_prompt must not call character_growth"
    )


# ---------------------------------------------------------------------------
# 3. consolidate_to_growth is NOT a slow_queue handler and is NOT enqueued
# ---------------------------------------------------------------------------

def test_consolidate_to_growth_not_registered_in_slow_queue():
    """slow_queue must not have a 'consolidate_to_growth' handler registered."""
    from core import pipeline as _pipeline
    register_src = inspect.getsource(_pipeline.register_slow_handlers)
    assert "consolidate_to_growth" not in register_src, (
        "consolidate_to_growth must not be a slow_queue handler"
    )


def test_post_process_does_not_enqueue_growth():
    """pipeline.post_process must not enqueue character_growth tasks (code call, not comment)."""
    from core import pipeline as _pipeline
    src = inspect.getsource(_pipeline.Pipeline.post_process)
    assert not _has_growth_code_call(src), (
        "post_process must not contain character_growth code calls"
    )


# ---------------------------------------------------------------------------
# 4. resolver covers all core reality-scoped artifacts
# ---------------------------------------------------------------------------

def test_resolver_covers_history():
    from core.memory.path_resolver import resolve_path
    from core.memory.scope import MemoryScope
    scope = MemoryScope.reality_scope("u_audit", "yexuan")
    p = resolve_path(scope, "history")
    assert p.name == "history.json"


def test_resolver_covers_event_log(sandbox):
    from core.memory.path_resolver import resolve_path
    from core.memory.scope import MemoryScope
    scope = MemoryScope.reality_scope("u_audit", "yexuan")
    p = resolve_path(scope, "event_log")
    assert p.is_absolute()


def test_resolver_covers_mid_term():
    from core.memory.path_resolver import resolve_path
    from core.memory.scope import MemoryScope
    scope = MemoryScope.reality_scope("u_audit", "yexuan")
    p = resolve_path(scope, "mid_term")
    assert p.name == "mid_term.json"


def test_resolver_covers_episodic():
    from core.memory.path_resolver import resolve_path
    from core.memory.scope import MemoryScope
    scope = MemoryScope.reality_scope("u_audit", "yexuan")
    p = resolve_path(scope, "episodic")
    assert p.name == "episodic.json"


def test_resolver_covers_memory_index():
    from core.memory.path_resolver import resolve_path
    from core.memory.scope import MemoryScope
    scope = MemoryScope.reality_scope("u_audit", "yexuan")
    p = resolve_path(scope, "memory_index")
    assert p.name == "memory_index.json"


def test_resolver_covers_fixation_state():
    from core.memory.path_resolver import resolve_path
    from core.memory.scope import MemoryScope
    scope = MemoryScope.reality_scope("u_audit", "yexuan")
    p = resolve_path(scope, "fixation_state")
    assert p.name == "fixation_state.json"


def test_resolver_covers_profile():
    from core.memory.path_resolver import resolve_path
    from core.memory.scope import MemoryScope
    scope = MemoryScope.reality_scope("u_audit", "yexuan")
    p = resolve_path(scope, "profile")
    assert p.name == "profile.json"


def test_resolver_covers_identity():
    from core.memory.path_resolver import resolve_path
    from core.memory.scope import MemoryScope
    scope = MemoryScope.reality_scope("u_audit", "yexuan")
    p = resolve_path(scope, "identity")
    assert p.name == "identity.yaml"


def test_resolver_covers_hidden_state():
    from core.memory.path_resolver import resolve_path
    from core.memory.scope import MemoryScope
    scope = MemoryScope.reality_scope("u_audit", "yexuan")
    p = resolve_path(scope, "hidden_state")
    assert p.name == "hidden_state.json"


def test_resolver_covers_afterglow_residue():
    from core.memory.path_resolver import resolve_path
    from core.memory.scope import MemoryScope
    scope = MemoryScope.reality_scope("u_audit", "yexuan")
    p = resolve_path(scope, "afterglow_residue")
    assert p.name == "afterglow_residue.json"


# ---------------------------------------------------------------------------
# 5. character_growth is legacy/dead — allowlisted non-blockers
# ---------------------------------------------------------------------------

def test_character_growth_not_imported_in_pipeline():
    """pipeline.py must not import or call character_growth (stale comments in docstrings allowed)."""
    from core import pipeline as _pipeline
    src = inspect.getsource(_pipeline)
    assert not _has_growth_code_call(src), (
        "pipeline must not import or call character_growth in code "
        "(stale doc-comment references are allowlisted by _has_growth_code_call)"
    )


def test_get_growth_tool_category_is_memory_not_info():
    """get_growth must have category='memory', keeping it out of the pre-pipeline probe."""
    from core.tool_dispatcher import _TOOL_REGISTRY
    spec = _TOOL_REGISTRY.get("get_growth")
    assert spec is not None, "get_growth must be registered"
    assert spec["category"] == "memory", (
        "get_growth must not be category='info' or 'desktop' (would expose character_growth to probe)"
    )


def test_probe_prompt_does_not_include_get_growth():
    """Pre-pipeline probe must not expose get_growth (which would activate character_growth path)."""
    from core.tool_dispatcher import get_probe_prompt
    probe = get_probe_prompt("home")
    assert "get_growth" not in probe, (
        "get_growth must not appear in probe (character_growth path must remain dormant)"
    )


# ---------------------------------------------------------------------------
# 6. No new production yexuan hardcoded fallback in migrated stores
# ---------------------------------------------------------------------------

def test_short_term_module_no_hardcoded_yexuan_path():
    """short_term path functions must not hardcode 'yexuan' as a path segment."""
    from core.memory import short_term
    for func in (short_term._history_path, short_term._history_write_path):
        src = inspect.getsource(func)
        assert '"yexuan"' not in src.replace("char_id: str = \"yexuan\"", ""), (
            f"{func.__name__} must not hardcode 'yexuan' as a path literal"
        )


def test_mid_term_module_no_hardcoded_yexuan_path():
    from core.memory import mid_term
    for func in (mid_term._read_file, mid_term._write_file):
        src = inspect.getsource(func)
        assert '"yexuan"' not in src.replace("char_id: str = \"yexuan\"", ""), (
            f"{func.__name__} must not hardcode 'yexuan' as a path literal"
        )


def test_event_log_module_no_hardcoded_yexuan_path():
    from core.memory import event_log
    for func in (event_log._event_log_write_dir, event_log._event_log_read_dir):
        src = inspect.getsource(func)
        assert '"yexuan"' not in src.replace("char_id: str = \"yexuan\"", ""), (
            f"{func.__name__} must not hardcode 'yexuan' as a path literal"
        )


def test_episodic_memory_no_hardcoded_yexuan_path():
    from core.memory import episodic_memory
    for func in (
        episodic_memory._mem_read_file,
        episodic_memory._mem_write_file,
        episodic_memory._index_read_file,
    ):
        src = inspect.getsource(func)
        assert '"yexuan"' not in src.replace("char_id: str = \"yexuan\"", ""), (
            f"{func.__name__} must not hardcode 'yexuan' as a path literal"
        )


def test_hidden_state_store_no_hardcoded_yexuan_path():
    from core.memory import user_hidden_state_store
    for func in (
        user_hidden_state_store.load_hidden_state,
        user_hidden_state_store.save_hidden_state,
        user_hidden_state_store._load_afterglow_raw,
    ):
        src = inspect.getsource(func)
        assert '"yexuan"' not in src.replace("char_id: str = \"yexuan\"", ""), (
            f"{func.__name__} must not hardcode 'yexuan' as a path literal"
        )


def test_user_profile_no_hardcoded_yexuan_path():
    from core.memory import user_profile
    for func in (user_profile._profile_read_path, user_profile._profile_write_path):
        src = inspect.getsource(func)
        assert '"yexuan"' not in src.replace("char_id: str = \"yexuan\"", ""), (
            f"{func.__name__} must not hardcode 'yexuan' as a path literal"
        )


def test_user_identity_no_hardcoded_yexuan_path():
    from core.memory import user_identity
    for func in (user_identity._identity_read_file, user_identity._identity_write_file):
        src = inspect.getsource(func)
        assert '"yexuan"' not in src.replace("char_id: str = \"yexuan\"", ""), (
            f"{func.__name__} must not hardcode 'yexuan' as a path literal"
        )
