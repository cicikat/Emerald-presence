"""
core/memory/user_hidden_state_store.py
======================================
Phase 1.5 — UserHiddenState persistence (load / save).

SECURITY NOTE — WriteEnvelope gate:
  This store does NOT enforce envelope gating.  It is the caller's
  responsibility to hold a WriteEnvelope with can_write_memory=True
  before calling save_hidden_state().  The store is intentionally
  policy-free so that callers supply their own envelope logic without
  re-implementing path handling.

  Future callers: you MUST have obtained a WriteEnvelope with
  can_write_memory=True before calling save_hidden_state().
  This store does not check or stamp envelopes.

Not wired to:
  - Dream (any path)
  - build_snapshot
  - scheduler
  - automatic save
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from core.memory.user_hidden_state import (
    UserHiddenState,
    default_hidden_state,
    from_dict,
    to_dict,
)
from core.safe_write import safe_write_json
from core.sandbox import get_paths

logger = logging.getLogger(__name__)

HIDDEN_STATE_FILENAME = "hidden_state.json"


def load_hidden_state(uid: str | int) -> UserHiddenState:
    """Load UserHiddenState for uid from disk.

    Returns default_hidden_state() if the file does not exist or is
    corrupted.  Never raises.

    SECURITY NOTE: Callers MUST hold a WriteEnvelope with
    can_write_memory=True before mutating and persisting the returned
    state.  This function is read-only and does not emit a
    WriteEnvelope stamp.

    Path: user_memory_root(uid) / hidden_state.json
    """
    path: Path = get_paths().user_memory_root(uid) / HIDDEN_STATE_FILENAME

    if not path.exists():
        return default_hidden_state()

    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("[hidden_state] cannot read %s: %s — returning default", path, exc)
        return default_hidden_state()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning("[hidden_state] corrupt JSON in %s: %s — returning default", path, exc)
        return default_hidden_state()

    try:
        return from_dict(data)
    except Exception as exc:
        logger.warning("[hidden_state] from_dict failed for %s: %s — returning default", path, exc)
        return default_hidden_state()


def save_hidden_state(uid: str | int, state: UserHiddenState) -> bool:
    """Persist UserHiddenState for uid using an atomic write.

    Returns True on success, False on I/O error.  Never raises.

    SECURITY NOTE: Callers MUST already hold a WriteEnvelope with
    can_write_memory=True before calling this function.  This store
    does NOT enforce the envelope gate — that responsibility belongs
    to the caller (e.g., the Reality-side integrator).

    Path: user_memory_root(uid) / hidden_state.json
    """
    path: Path = get_paths().user_memory_root(uid) / HIDDEN_STATE_FILENAME
    data = to_dict(state)
    ok = safe_write_json(path, data)
    if not ok:
        logger.error("[hidden_state] save failed for uid=%s", uid)
    return ok
