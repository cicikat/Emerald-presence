"""
记忆管理路由
"""

from fastapi import APIRouter, Depends, HTTPException

from admin.auth import verify_token

router = APIRouter()


# ── 短期记忆 ──────────────────────────────────────────────────────────────────

@router.get("/{user_id}/short-term", summary="获取短期记忆")
async def get_short_term(user_id: str, auth=Depends(verify_token)):
    """返回用户最近的对话历史（滚动窗口内的全部消息）"""
    from core.memory import short_term
    history = short_term.load(user_id)
    return {"user_id": user_id, "history": history, "count": len(history)}


@router.delete("/{user_id}/short-term", summary="清除短期记忆")
async def clear_short_term(user_id: str, auth=Depends(verify_token)):
    """清空用户短期对话历史（写入空列表）"""
    from core.memory import short_term
    short_term.clear(user_id)
    return {"message": f"用户 {user_id} 短期记忆已清除"}


# TODO(Step 8): GET /fixation/status?uid=...
#   返回该 uid 的 fixation_state + 最近 20 条 fixation.jsonl 日志。
#   实现要点：
#     from core.memory.fixation_pipeline import _load_fixation_state, _should_consolidate
#     from core.sandbox import get_paths
#     log_path = get_paths().fixation_log()
#     lines = log_path.read_text(encoding="utf-8").splitlines()[-20:] if log_path.exists() else []
#     records = [json.loads(l) for l in lines if f'"uid": "{uid}"' in l]
#     return {"fixation_state": _load_fixation_state(uid), "recent_logs": records}
