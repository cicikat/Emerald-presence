"""
活动状态路由
"""

from datetime import datetime

from fastapi import APIRouter, Depends

from admin.auth import verify_token
from core import activity_manager

router = APIRouter()


@router.get("/current", summary="获取当前活动状态")
async def get_activity_state(auth=Depends(verify_token)):
    state = activity_manager.get_current()

    started_at = None
    raw = state.get("started_at")
    if raw:
        try:
            started_at = datetime.fromisoformat(raw).timestamp()
        except Exception:
            pass

    return {
        "id": None,
        "text": state.get("current"),
        "arc": state.get("arc"),
        "started_at": started_at,
        "next_switch_at": state.get("expected_until_ts"),
        "thinking_about_eligible": bool(state.get("thinking_about")),
    }
