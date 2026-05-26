"""
Per-uid dream session settings.

These switches control ONLY what goes into the frozen snapshot at dream entry.
They NEVER open live memory access during the dream — that is always blocked.

amnesia=False means "include pre-dream memories in snapshot, not "enable live recall".
All-off (amnesia=True, keep_impression=False, enable_dream_lorebook=False):
  snapshot = character card + world book + jailbreak only — sandbox AIRP mode.
"""

import json
import logging
from typing import Any

from core.safe_write import safe_write_json
from core.sandbox import get_paths, safe_user_id

logger = logging.getLogger(__name__)

_DEFAULTS: dict[str, Any] = {
    "enable_dream_lorebook": True,
    "amnesia": False,           # False = include pre-dream memory in snapshot
    "keep_impression": True,    # True = include user profile impression in snapshot
    # Reserved seam — not consumed in MVP1
    "lucid_mode": "lucid_shared",
}


def _path(user_id: str | int):
    return get_paths().dream_settings_path(user_id)


def load(user_id: str | int) -> dict[str, Any]:
    path = _path(user_id)
    if not path.exists():
        return dict(_DEFAULTS)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return dict(_DEFAULTS)
        return {**_DEFAULTS, **data}
    except Exception as e:
        logger.warning(f"[dream_settings] read failed uid={user_id}: {e}")
        return dict(_DEFAULTS)


def save(user_id: str | int, settings: dict[str, Any]) -> bool:
    merged = {**_DEFAULTS, **settings}
    p = _path(user_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    return safe_write_json(p, merged)


def set_field(user_id: str | int, key: str, value: Any) -> bool:
    s = load(user_id)
    s[key] = value
    return save(user_id, s)
