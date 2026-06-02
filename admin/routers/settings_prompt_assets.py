"""
Prompt Asset 配置 API
GET  /settings/prompt-assets  — 读取可用资产列表 + 当前激活配置
PATCH /settings/prompt-assets — 部分更新激活配置，并热重载 lore_engine
"""

import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from admin.auth import verify_token
from core.sandbox import get_paths

router = APIRouter()

_CHARACTERS_DIR = Path("characters")

# 文件名包含这些关键词时排除（不是角色卡）
_EXCLUDE_KEYWORDS = ("template", "author_notes")


def _list_characters() -> list[dict]:
    """Scan characters/*.json, return {id, label} dicts for actual character cards.
    id   = file stem (used in active_character storage and validation)
    label = name field from the JSON card, fallback to stem
    """
    if not _CHARACTERS_DIR.exists():
        return []
    result = []
    for p in sorted(_CHARACTERS_DIR.glob("*.json")):
        stem_lower = p.stem.lower()
        if any(kw in stem_lower for kw in _EXCLUDE_KEYWORDS):
            continue
        label = p.stem
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            label = data.get("name") or p.stem
        except Exception:
            pass
        result.append({"id": p.stem, "label": label})
    return result


def _character_ids() -> list[str]:
    """Return just the id stems for validation."""
    return [c["id"] for c in _list_characters()]


def _list_lorebooks() -> list[str]:
    d = get_paths().lorebooks_dir()
    if not d.exists():
        return []
    return sorted(p.stem for p in d.glob("*.yaml"))


def _list_jailbreaks() -> list[str]:
    d = get_paths().jailbreaks_dir()
    if not d.exists():
        return []
    return sorted(p.stem for p in d.glob("*.json"))


def _read_active() -> dict:
    p = get_paths().active_prompt_assets()
    return json.loads(p.read_text(encoding="utf-8"))


def _write_active(data: dict):
    p = get_paths().active_prompt_assets()
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _reload_lore_engine():
    try:
        from core.pipeline_registry import get as _get_pipeline
        pipeline = _get_pipeline()
        if pipeline is not None and hasattr(pipeline, "lore_engine"):
            pipeline.lore_engine.load()
    except Exception:
        pass


def _validate_stem(value: str, valid_stems: list[str], field: str):
    """Reject path separators, dots (extensions / traversal), and unknown stems."""
    if "/" in value or "\\" in value or "." in value:
        raise HTTPException(
            status_code=422,
            detail=f"{field}: 不接受路径分隔符或扩展名（拒绝：{value!r}）",
        )
    if value not in valid_stems:
        raise HTTPException(
            status_code=422,
            detail=f"{field}: {value!r} 不在可用列表中（可用：{valid_stems}）",
        )


@router.get("/settings/prompt-assets", summary="获取 Prompt 资产列表与激活配置")
async def get_prompt_assets(auth=Depends(verify_token)):
    return {
        "characters": _list_characters(),
        "lorebooks":  _list_lorebooks(),
        "jailbreaks": _list_jailbreaks(),
        "active":     _read_active(),
    }


class PromptAssetsUpdate(BaseModel):
    active_character:   Optional[str]       = None
    enabled_lorebooks:  Optional[list[str]] = None
    enabled_jailbreaks: Optional[list[str]] = None


@router.patch("/settings/prompt-assets", summary="部分更新 Prompt 资产激活配置")
async def patch_prompt_assets(body: PromptAssetsUpdate, auth=Depends(verify_token)):
    if (
        body.active_character is None
        and body.enabled_lorebooks is None
        and body.enabled_jailbreaks is None
    ):
        raise HTTPException(status_code=422, detail="至少提供一个更新字段")

    if body.active_character is not None:
        _validate_stem(body.active_character, _character_ids(), "active_character")

    if body.enabled_lorebooks is not None:
        valid_lb = _list_lorebooks()
        for stem in body.enabled_lorebooks:
            _validate_stem(stem, valid_lb, "enabled_lorebooks")

    if body.enabled_jailbreaks is not None:
        valid_jb = _list_jailbreaks()
        for stem in body.enabled_jailbreaks:
            _validate_stem(stem, valid_jb, "enabled_jailbreaks")

    active = _read_active()
    if body.active_character is not None:
        active["active_character"] = body.active_character
    if body.enabled_lorebooks is not None:
        active["enabled_lorebooks"] = body.enabled_lorebooks
    if body.enabled_jailbreaks is not None:
        active["enabled_jailbreaks"] = body.enabled_jailbreaks

    _write_active(active)

    if body.enabled_lorebooks is not None:
        _reload_lore_engine()

    return {"message": "已更新", "active": active}
