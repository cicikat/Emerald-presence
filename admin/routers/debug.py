"""
[DEV-ONLY] debug 路由 — 本地手动验证用，不走 LLM，不写存储。

TODO: 确认 message_segments 集成稳定后可移除此文件及 admin_server.py 中的注册行。
"""

import asyncio
import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from admin.auth import verify_token
import channels.desktop_ws as desktop_ws

logger = logging.getLogger(__name__)

router = APIRouter()

_TEST_RAW     = "<say>你好</say>"
_TEST_CONTENT = "你好"
_TEST_SEGMENTS = [{"type": "say", "text": "你好"}]


@router.post(
    "/debug/ws-segments-test",
    summary="[DEV] 推送 channel_message + message_segments 测试包",
    description=(
        "向已连接的桌宠端 WS 推送一对固定测试消息，用于验证前端 message_segments 洗标签逻辑。\n\n"
        "- channel_message.content = '<say>你好</say>'\n"
        "- message_segments.content = '你好'\n"
        "- 两条消息共享同一个 msg_id\n\n"
        "**仅用于本地开发验证，不走 LLM，不写任何存储。**"
    ),
    tags=["Debug"],
)
async def ws_segments_test(auth=Depends(verify_token)):
    if not desktop_ws.is_connected():
        logger.warning("[debug] ws-segments-test: 桌宠端 WS 未连接")
        return JSONResponse(
            status_code=503,
            content={"ok": False, "error": "桌宠端 WS 未连接，请先打开 Emerald-client"},
        )

    # 两条消息共享同一个 msg_id，模拟真实发送时序
    msg_id = desktop_ws._new_msg_id()

    sent_msg = await desktop_ws.push_message(_TEST_RAW, msg_id=msg_id)
    if not sent_msg:
        return JSONResponse(
            status_code=502,
            content={"ok": False, "error": "channel_message 发送失败"},
        )

    # 小延迟模拟真实场景（LLM 解析 segments 需要少量时间）
    await asyncio.sleep(0.05)

    sent_seg = await desktop_ws.push_segments(
        _TEST_CONTENT, _TEST_SEGMENTS, msg_id=msg_id
    )

    logger.info(
        f"[debug] ws-segments-test 完成: msg_id={msg_id} "
        f"channel_message={'ok' if sent_msg else 'fail'} "
        f"message_segments={'ok' if sent_seg else 'fail'}"
    )

    return {
        "ok": True,
        "msg_id": msg_id,
        "channel_message_sent": sent_msg,
        "message_segments_sent": sent_seg,
        "raw": _TEST_RAW,
        "content": _TEST_CONTENT,
        "segments": _TEST_SEGMENTS,
    }
