"""
情绪状态路由
"""
import json

from fastapi import APIRouter, Depends, HTTPException

from admin.auth import verify_token
from core.memory import mood_state
from core.sandbox import get_paths as _get_paths

router = APIRouter()


def _active_char_id() -> str:
    try:
        raw = json.loads(_get_paths().active_prompt_assets().read_text(encoding="utf-8"))
        cid = (raw.get("active_character") or "").strip()
    except Exception:
        raise HTTPException(status_code=503, detail="active character unavailable")

    if not cid:
        raise HTTPException(status_code=503, detail="active_character missing")

    from core.asset_registry import get_registry
    try:
        get_registry().resolve(cid, "character")
    except ValueError:
        raise HTTPException(status_code=422, detail=f"unknown character id: {cid!r}")

    return cid


@router.get("/state", summary="获取情绪状态")
async def get_mood_state(auth=Depends(verify_token)):
    return mood_state.load(char_id=_active_char_id())
