"""
Group Dream settings — Brief 100 §1/§3.

Schema (all fields optional on PATCH; merged over _DEFAULTS on load, so disk
always round-trips full-field, same pattern as core.dream.dream_settings):

    {
      "world_layer": "reality_derived",
      "enable_dream_lorebook": true,
      "boundary_level": "body_perceptible",
      "jailbreak_presets": ["default"],
      "per_char": {"<char_id>": {"jailbreak_presets": ["..."]}}
    }

D0 fallback chain (Brief 100 §1): per_char[char_id].jailbreak_presets →
group-level jailbreak_presets → default.md. The first two links are resolved
by `resolve_jailbreak_presets()` here; the last link (named preset missing →
default.md → disabled) is handled inside
`core.dream.dream_pipeline._load_presets_text()`, reused as-is.

v1 hardwires `max_reactions=0` / `topic_seed_prob=0` at the Stage-settings
level (see core.stage.dream_runtime._load_stage_fn) rather than here — those
are StageSettings fields (Phase R/T knobs), not part of this schema, and are
never exposed through this settings surface.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from core.safe_write import safe_write_json
from core.sandbox import get_paths

logger = logging.getLogger(__name__)

_DEFAULTS: dict[str, Any] = {
    "world_layer": "reality_derived",
    "enable_dream_lorebook": True,
    "boundary_level": "body_perceptible",
    "jailbreak_presets": ["default"],
    "per_char": {},
}


def load(group_id: str) -> dict[str, Any]:
    path = get_paths().dream_group_settings_path(group_id=group_id)
    if not path.exists():
        import copy
        return copy.deepcopy(_DEFAULTS)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("settings must be a dict")
    except Exception as e:
        logger.warning(f"[stage.dream_settings] read failed group={group_id}: {e}")
        import copy
        return copy.deepcopy(_DEFAULTS)
    merged = {**_DEFAULTS, **data}
    if not isinstance(merged.get("per_char"), dict):
        merged["per_char"] = {}
    return merged


def save(group_id: str, settings: dict[str, Any]) -> dict[str, Any]:
    merged = {**_DEFAULTS, **settings}
    if not isinstance(merged.get("per_char"), dict):
        merged["per_char"] = {}
    path = get_paths().dream_group_settings_path(group_id=group_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    safe_write_json(path, merged)
    return merged


def resolve_jailbreak_presets(settings: dict[str, Any], char_id: str) -> list[str]:
    """D0 fallback chain, first two links: per_char[char_id] → group-level.

    Never returns an empty list — group-level `jailbreak_presets` always has
    at least the schema default (["default"]), so the final "default.md
    missing too" disabled case is only ever reached inside
    `_load_presets_text()`, never here.
    """
    per_char = settings.get("per_char") or {}
    entry = per_char.get(char_id) or {}
    presets = entry.get("jailbreak_presets")
    if isinstance(presets, list) and presets:
        return [str(p) for p in presets]
    group_presets = settings.get("jailbreak_presets")
    if isinstance(group_presets, list) and group_presets:
        return [str(p) for p in group_presets]
    return ["default"]
