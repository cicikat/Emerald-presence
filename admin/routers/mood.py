"""
情绪状态路由
"""

from fastapi import APIRouter, Depends

from admin.auth import verify_token
from core.memory import mood_state

router = APIRouter()


@router.get("/state", summary="获取情绪状态")
async def get_mood_state(auth=Depends(verify_token)):
    return mood_state.load()
