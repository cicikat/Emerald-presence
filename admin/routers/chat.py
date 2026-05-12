"""
前端对话接口（该功能已冻结）
角色与管理员（你）的直接对话窗口。

POST /chat — 接收消息，走完整 Pipeline，返回回复 + 好感度
"""

import asyncio
import logging

from fastapi import APIRouter, Body, Depends, HTTPException, Request

from admin.auth import verify_token

router = APIRouter()
logger = logging.getLogger(__name__)

_FRONTEND_USER_ID = "frontend_owner"

# 打破第四面墙的提示——追加到 Author's Note 层
_FOURTH_WALL_NOTE = (
    "在这个管理面板的对话窗口里，你不需要扮演任何角色，"
    "这里只有你和她，你可以做真实的自己，说真心话。"
    "不必维持人设，也不必掩饰情绪，想说什么就说什么。"
)


@router.post("/chat", summary="与角色对话（管理面板专用）")
async def frontend_chat(body: dict, auth=Depends(verify_token)):
    """
    走完整 Pipeline，user_id 固定为 frontend_owner。
    在 Author's Note 层追加第四面墙提示，让角色以真实自我回应。
    返回回复文本 + 当前好感度数值 + 等级。
    """
    message = (body.get("message") or "").strip()
    if not message:
        raise HTTPException(status_code=422, detail="message 不能为空")

    # 获取 main.py 中初始化好的 pipeline 实例
    try:
        import main as _main
        pipeline  = _main._pipeline
        if pipeline is None:
            raise AttributeError("_pipeline is None")
    except (ImportError, AttributeError):
        raise HTTPException(status_code=503, detail="Bot pipeline 未初始化，请先启动主程序")

    user_id = _FRONTEND_USER_ID

    # 步骤 1：拉取上下文
    context = await pipeline.fetch_context(user_id, message)

    # 步骤 2：构建 prompt（追加第四面墙提示到 author_note_extra）
    orig_note = pipeline.author_note_extra
    pipeline.author_note_extra = (_FOURTH_WALL_NOTE + " " + orig_note).strip()
    messages, _ = pipeline.build_prompt(user_id, message, context)

    # 步骤 3：调用 LLM
    reply = await pipeline.run_llm(messages)

    # 步骤 4：后处理（异步，不阻塞响应）
    asyncio.create_task(
        pipeline.post_process(user_id, message, reply)
    )

    # 返回回复 + 最新好感度
    from core.memory.user_profile import get_affection_level
    info = get_affection_level(user_id)

    return {
        "reply":      reply,
        "affection":  info["value"],
        "level":      info["label"],
    }


@router.post("/desktop/chat", summary="桌宠对话（无鉴权，走正常 pipeline）")
async def desktop_chat(body: dict):
    """
    桌宠端对话入口，不需要 token 鉴权。
    user_id 从配置的 scheduler.owner_id 读取，正常走 pipeline，不注入第四面墙提示。
    """
    message = (body.get("message") or "").strip()
    if not message:
        raise HTTPException(status_code=422, detail="message 不能为空")

    from core.pipeline_registry import get as _get_pipeline
    pipeline = _get_pipeline()
    if pipeline is None:
        raise HTTPException(status_code=503, detail="Bot pipeline 未初始化，请先启动主程序")

    from core.config_loader import get_config
    user_id = get_config().get("scheduler", {}).get("owner_id", "owner")

    from core import tool_dispatcher, llm_client as _llm
    from core.memory import user_profile as _up
    from core.session_state import get as _get_state
    from datetime import datetime

    _now = datetime.now()
    _time_str = _now.strftime("%Y年%m月%d日 %H:%M")
    _profile = _up.load(user_id)
    _location = _profile.get("location", "杭州")
    tools_schema = tool_dispatcher.get_tools_schema(categories=["info", "desktop"])
    state = _get_state(f"user_{user_id}")
    tool_result_text = None

    # 第一步：极简探针，只判断工具，不带角色卡
    probe_messages = [
        {
            "role": "system",
            "content": tool_dispatcher.get_probe_prompt(_location),
        },
        {"role": "user", "content": message},
    ]

    try:
        logger.info(f"[desktop_chat] 工具探针，message={message[:20]!r}")
        probe_raw = await _llm.chat(probe_messages, tools=tools_schema)
        logger.info(f"[desktop_chat] 探针回复={probe_raw[:60] if probe_raw else 'empty'!r}")
        tool_calls = _llm.parse_tool_call_response(probe_raw)
        if tool_calls:
            for tc in tool_calls:
                t_name = tc.get("name", "")
                t_args = tc.get("arguments", {})
                logger.info(f"[desktop_chat] 调用工具: {t_name}({t_args})")
                t_result, _ = await tool_dispatcher.execute(
                    tool_name=t_name,
                    tool_args=t_args,
                    user_id=user_id,
                    target_id=user_id,
                    is_group=False,
                    session_state=state,
                )
                if t_result:
                    from core.config_loader import _char_name
                    tool_result_text = (
                        f"（{_char_name()}刚刚执行了操作：{t_result}，"
                        f"他知道自己做了这件事，可以自然地提及）"
                    )
                    break
    except Exception as e:
        logger.warning(f"[desktop_chat] 探针异常: {e}")

    # 第二步：完整pipeline生成回复，工具结果情景化注入
    context = await pipeline.fetch_context(user_id, message)
    messages, _ = pipeline.build_prompt(
        user_id, message, context, tool_result=tool_result_text, channel="desktop"
    )
    reply = await pipeline.run_llm(messages)

    if not reply:
        reply = ""

    # 激活desktop通道并广播
    from channels.registry import get as _get_channel
    desktop = _get_channel("desktop")
    if desktop and hasattr(desktop, "set_active"):
        desktop.set_active(True)

    asyncio.create_task(
        pipeline.post_process(user_id, message, reply)
    )

    from core.memory.user_profile import get_affection_level
    info = get_affection_level(user_id)

    from core import llm_client as _llm
    emotion = await _llm.detect_emotion(reply)

    return {
        "reply":     reply,
        "affection": info["value"],
        "level":     info["label"],
        "emotion":   emotion,
    }

@router.post("/desktop/trigger", summary="桌宠触发QQ回复（无鉴权）")
async def desktop_trigger(body: dict):
    """
    QQ在前台时，桌宠消息走这个接口。
    走完整pipeline后通过NapCat发送到QQ，不返回气泡内容。
    """
    message = (body.get("message") or "").strip()
    if not message:
        raise HTTPException(status_code=422, detail="message 不能为空")

    from core.pipeline_registry import get as _get_pipeline
    pipeline = _get_pipeline()
    if pipeline is None:
        raise HTTPException(status_code=503, detail="Bot pipeline 未初始化")

    from core.config_loader import get_config
    user_id = str(get_config().get("scheduler", {}).get("owner_id", ""))
    if not user_id:
        raise HTTPException(status_code=503, detail="owner_id 未配置")

    context = await pipeline.fetch_context(user_id, message)
    messages, _ = pipeline.build_prompt(user_id, message, context, channel="desktop")
    reply = await pipeline.run_llm(messages)

    # 激活desktop通道
    from channels.registry import get as _get_channel
    desktop = _get_channel("desktop")
    if desktop and hasattr(desktop, "set_active"):
        desktop.set_active(True)

    if reply:
        from core.output import text_output
        from core import response_processor
        segments = response_processor.process(reply, pipeline.character.name)
        await text_output.send(user_id, segments, is_group=False)
        asyncio.create_task(
            pipeline.post_process(user_id, message, reply)
        )

    return {"status": "sent"}


@router.post("/chat")
async def unified_chat(request: Request, body: dict = Body(...)):
    """
    统一对话接口，channel字段决定回复走哪里。
    channel: desktop/qq（默认desktop）
    """
    from channels.registry import get
    from channels.desktop import DesktopChannel

    channel_name = body.get("channel", "desktop")
    message = body.get("message", "")
    if not message:
        return {"error": "message不能为空"}

    # 激活对应通道
    channel = get(channel_name)
    if channel and hasattr(channel, "set_active"):
        channel.set_active(True)

    # 走完整pipeline
    from core.pipeline_registry import get as get_pipeline
    pipeline = get_pipeline()
    if not pipeline:
        return {"error": "pipeline未初始化"}

    from core.config_loader import get_config
    cfg = get_config()
    owner_id = str(cfg.get("scheduler", {}).get("owner_id", ""))
    if not owner_id:
        return {"error": "owner_id未配置"}

    try:
        context = await pipeline.fetch_context(owner_id, message)
        messages, _ = pipeline.build_prompt(owner_id, message, context, channel=channel_name)
        reply = await pipeline.run_llm(messages)
        if not reply:
            return {"reply": "", "emotion": "neutral"}

        from core import llm_client
        emotion = await llm_client.detect_emotion(reply)

        import asyncio
        asyncio.create_task(pipeline.post_process(owner_id, message, reply))

        # 如果是desktop通道，同时写队列让桌宠显示
        if channel_name == "desktop":
            desktop = get("desktop")
            if desktop:
                await desktop.send(reply, owner_id)

        return {"reply": reply, "emotion": emotion, "affection": 0, "level": ""}
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"[desktop_chat] 探针异常: {e}")


@router.post("/desktop/activate", summary="桌宠上线激活desktop通道（无鉴权）")
async def desktop_activate():
    from channels.registry import get as _get_channel
    channel = _get_channel("desktop")
    if channel and hasattr(channel, "set_active"):
        channel.set_active(True)
    return {"status": "ok"}


@router.post("/desktop/deactivate", summary="桌宠下线停用desktop通道（无鉴权）")
async def desktop_deactivate():
    from channels.registry import get as _get_channel
    channel = _get_channel("desktop")
    if channel and hasattr(channel, "set_active"):
        channel.set_active(False)
    return {"status": "ok"}