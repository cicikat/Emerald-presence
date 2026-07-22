"""
Group Dream (Dream Stage) shared state — Brief 100 §1.

Physically separate from both `core.dream.dream_state` (single-person, keyed
by uid) and `core.stage.store` (reality Stage meta/transcript). Keyed by
`group_id` only — there is exactly one shared dream_state.json per group,
never per (group_id, uid), since v1 has a single owner per group.

Reuses `core.dream.dream_state.DreamStatus` / `DREAM_ARTIFACT_SENTINEL` /
`apply_dream_artifact_sentinel` / `derive_dream_state_projection` — the state
machine vocabulary and UI projection logic are domain-agnostic; only the
storage path and the per-char fields differ from the solo schema.

v1 has no soft retention and no afterglow (Brief 100 §0 "零回流", "hard_exit
绝对"): a group dream never enters REALITY_AFTERGLOW. Hard exit returns the
group directly to REALITY_CHAT once the transcript is archived.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from core.dream.dream_state import DreamStatus, apply_dream_artifact_sentinel  # noqa: F401  (re-exported)
from core.safe_write import safe_write_json
from core.sandbox import get_paths, safe_user_id

logger = logging.getLogger(__name__)

_ACTIVE_STATUSES: frozenset[str] = frozenset({
    DreamStatus.DREAM_ACTIVE.value,
    DreamStatus.DREAM_CLOSING.value,
})


def default_state(group_id: str, owner_uid: str | None = None) -> dict[str, Any]:
    state: dict[str, Any] = {
        "group_id": safe_user_id(group_id),
        "status": DreamStatus.REALITY_CHAT.value,
    }
    if owner_uid is not None:
        state["owner_uid"] = str(owner_uid)
    return state


def read_state(group_id: str) -> dict[str, Any]:
    path = get_paths().dream_group_state_path(group_id=group_id)
    if not path.exists():
        return default_state(group_id)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"[stage.dream_state] read failed group={group_id}: {e}")
        return default_state(group_id)
    if not isinstance(data, dict):
        logger.warning(f"[stage.dream_state] invalid state shape group={group_id}")
        return default_state(group_id)
    status = data.get("status")
    if status not in {item.value for item in DreamStatus}:
        logger.warning(f"[stage.dream_state] unknown status group={group_id}: {status!r}")
        return default_state(group_id)
    data.setdefault("group_id", safe_user_id(group_id))
    return data


def write_state(group_id: str, state: dict[str, Any]) -> bool:
    if not isinstance(state, dict):
        raise TypeError("group dream state must be a dict")
    status = state.get("status")
    if isinstance(status, DreamStatus):
        state = {**state, "status": status.value}
        status = state["status"]
    if status not in {item.value for item in DreamStatus}:
        raise ValueError(f"unknown dream status: {status!r}")
    payload = {**state, "group_id": safe_user_id(group_id)}
    path = get_paths().dream_group_state_path(group_id=group_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    return safe_write_json(path, payload)


def is_active(group_id: str) -> bool:
    """True iff this group currently has a live dream (ACTIVE or CLOSING)."""
    return read_state(group_id).get("status") in _ACTIVE_STATUSES


def has_active_group_dream_for_owner(owner_uid: str) -> bool:
    """Scan every group dream for one owned by `owner_uid` that is ACTIVE/CLOSING.

    Used by both directions of the mutual-exclusion invariant (Brief 100 §3):
    a solo `/dream/enter` must be rejected while any of the owner's groups is
    dreaming, and `/group/{id}/dream/enter` must be rejected while the owner's
    solo dream is ACTIVE/CLOSING (the latter check lives in the dream router,
    reusing `core.dream.dream_state.read_state` directly).

    Fail-closed at the directory-scan level (cannot enumerate → block, since
    "uncertain" must never silently mean "allowed"); fail-open per individual
    group file (a corrupt neighboring group's state must not block this
    owner's real dream state — read_state() already degrades that file to a
    safe default).
    """
    root = get_paths().dream_group_root_dir()
    try:
        if not root.exists():
            return False
        group_dirs = [d for d in root.iterdir() if d.is_dir()]
    except Exception as exc:
        logger.error("[stage.dream_state] group dream scan failed owner=%s: %s", owner_uid, exc)
        return True  # BLOCK_UNCERTAIN-equivalent: cannot rule out an active group dream
    for group_dir in group_dirs:
        state = read_state(group_dir.name)
        if state.get("status") in _ACTIVE_STATUSES and str(state.get("owner_uid") or "") == str(owner_uid):
            return True
    return False


# ── Dream-local volatile state helpers (mirrors core.dream.dream_state) ──────

def get_local_state(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "char_tension": dict(state.get("char_tension") or {}),
        "scene_state": state.get("scene_state"),
        "symbolic_anchors": list(state.get("symbolic_anchors") or []),
        "body_state": state.get("body_state") or {},
    }


def patch_local_state(
    state: dict[str, Any],
    *,
    char_tension: dict[str, float] | None = None,
    scene_state: str | None = None,
    symbolic_anchors: list[str] | None = None,
    body_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    updated = dict(state)
    if char_tension is not None:
        updated["char_tension"] = {
            str(k): max(0.0, min(1.0, float(v))) for k, v in char_tension.items()
        }
    if scene_state is not None:
        updated["scene_state"] = scene_state
    if symbolic_anchors is not None:
        updated["symbolic_anchors"] = list(symbolic_anchors)
    if body_state is not None:
        updated["body_state"] = body_state
    return updated


def clear_local_state(state: dict[str, Any]) -> dict[str, Any]:
    """Strip dream-local volatile fields (call at group dream close)."""
    out = dict(state)
    for key in (
        "char_tension", "scene_state", "symbolic_anchors", "body_state",
        "per_char_snapshots", "frozen_relations", "dream_id", "dream_started_at",
        "frozen_world", "active_round_id", "round_started_at", "round_status",
        "last_round_error",
    ):
        out.pop(key, None)
    return out
