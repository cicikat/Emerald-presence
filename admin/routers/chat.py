"""
前端对话接口（该功能已冻结）
角色与管理员（你）的直接对话窗口。

POST /chat — 接收消息，走完整 Pipeline，返回回复 + 好感度
"""

import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Request, UploadFile

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


async def run_owner_chat_turn(message: str, channel_name: str) -> dict:
    """
    手机/桌宠共用的 owner 对话入口。
    conversation_lock 覆盖 fetch_context → LLM → critical post_process，
    保证同一用户多端输入不会并行读取旧上下文。
    """
    from core.pipeline_registry import get as _get_pipeline
    pipeline = _get_pipeline()
    if pipeline is None:
        raise HTTPException(status_code=503, detail="Bot pipeline 未初始化，请先启动主程序")

    from core.config_loader import get_config
    user_id = str(get_config().get("scheduler", {}).get("owner_id", "owner"))
    if not user_id:
        raise HTTPException(status_code=503, detail="owner_id 未配置")

    from core.conversation_gate import conversation_lock

    async with conversation_lock(user_id):
        tool_result_text = await _probe_and_execute_tools(message, user_id)

        context = await pipeline.fetch_context(user_id, message)
        messages, _ = pipeline.build_prompt(
            user_id,
            message,
            context,
            tool_result=tool_result_text,
            channel=channel_name,
        )
        reply = await pipeline.run_llm(messages)
        if not reply:
            reply = ""

        from channels.registry import get as _get_channel
        channel = _get_channel(channel_name)
        if channel and hasattr(channel, "set_active"):
            channel.set_active(True)

        post_info = await pipeline.post_process(user_id, message, reply)

        from core.memory.user_profile import get_affection_level
        info = get_affection_level(user_id)

        return {
            "reply": reply,
            "affection": info["value"],
            "level": info["label"],
            "emotion": (post_info or {}).get("emotion", "neutral"),
            "turn_id": (post_info or {}).get("turn_id", ""),
            "critical_written": (post_info or {}).get("critical_written", False),
        }


async def _probe_and_execute_tools(message: str, user_id: str) -> str | None:
    from core import tool_dispatcher, llm_client as _llm
    from core.memory import user_profile as _up
    from core.session_state import get as _get_state

    _profile = _up.load(user_id)
    _location = _profile.get("location", "杭州")
    tools_schema = tool_dispatcher.get_tools_schema(categories=["info", "desktop"])
    state = _get_state(f"user_{user_id}")
    probe_messages = [
        {
            "role": "system",
            "content": tool_dispatcher.get_probe_prompt(_location),
        },
        {"role": "user", "content": message},
    ]

    try:
        logger.info(f"[owner_chat] 工具探针，channel消息={message[:20]!r}")
        probe_raw = await _llm.chat(probe_messages, tools=tools_schema)
        logger.info(f"[owner_chat] 探针回复={probe_raw[:60] if probe_raw else 'empty'!r}")
        tool_calls = _llm.parse_tool_call_response(probe_raw)
        if not tool_calls:
            return None

        for tc in tool_calls:
            t_name = tc.get("name", "")
            t_args = tc.get("arguments", {})
            logger.info(f"[owner_chat] 调用工具: {t_name}({t_args})")
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

                return (
                    f"（{_char_name()}刚刚执行了操作：{t_result}，"
                    f"他知道自己做了这件事，可以自然地提及）"
                )
    except Exception as e:
        logger.warning(f"[owner_chat] 探针异常: {e}")
    return None


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

    result = await run_owner_chat_turn(message, "desktop")

    from core.scheduler.sensor_events import notify_chat_happened
    notify_chat_happened()

    return result


@router.post("/upload/ingest", summary="三端统一文件上传入口(无鉴权)")
async def upload_ingest(
    file: UploadFile | None = File(None),
    files: list[UploadFile] | None = File(None),
    message: str = Form(""),
    channel: str = Form("desktop"),
):
    """
    multipart 上传 + 可选用户附言 + channel 标记。
    """
    from core import media_processor

    upload_files = [file] if file else (files or [])
    if not upload_files:
        raise HTTPException(status_code=422, detail="文件不能为空")

    suffixes = [Path(item.filename or "").suffix.lower() for item in upload_files]
    is_docs = [suffix in media_processor.SUPPORTED_SUFFIXES for suffix in suffixes]
    is_images = [suffix in media_processor.SUPPORTED_IMAGE_SUFFIXES for suffix in suffixes]

    if any(is_docs) and any(is_images):
        raise HTTPException(status_code=422, detail="不支持文档和图片混合上传")

    if all(is_docs):
        if len(upload_files) > 1:
            raise HTTPException(status_code=422, detail="文档只支持单个上传")

        one_file = upload_files[0]
        data = await one_file.read()
        fname = one_file.filename or "文件"
        if len(data) > 5 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="文件超过 5MB 上限")

        result = await media_processor.ingest_file_bytes(data, fname)
        if result is None:
            raise HTTPException(status_code=422, detail="文件读取失败")

        text, stored_path = result

        media_context = (
            f"(你发来了一个文件:{fname},内容如下),回应必须细腻且有分量。"
            f"回应长度不少于150字,不要因为克制就缩短回应。\n{text[:3000]}"
        )
        full_message = media_context + ("\n" + message if message else "")
        response = await run_owner_chat_turn(full_message, channel)
        response["stored_path"] = str(stored_path)
        return response

    if all(is_images):
        items = []
        for item in upload_files:
            data = await item.read()
            if len(data) > media_processor.MAX_IMAGE_SIZE:
                raise HTTPException(status_code=413, detail="图片超过 10MB 上限")
            items.append((data, item.filename or "image"))

        descriptions = await media_processor.ingest_image_bytes(items)
        if descriptions is None:
            raise HTTPException(status_code=422, detail="图片识别失败")

        if len(descriptions) == 1:
            media_context = f"(你看到了用户发来的一张图,内容:{descriptions[0]})"
        else:
            lines = "\n".join(f"图{i + 1}:{desc}" for i, desc in enumerate(descriptions))
            media_context = f"(你看到了用户发来的{len(descriptions)}张图,内容如下:\n{lines})"
        full_message = media_context + ("\n" + message if message else "")
        response = await run_owner_chat_turn(full_message, channel)
        response["stored_paths"] = media_processor.LAST_IMAGE_STORED_PATHS
        return response

    raise HTTPException(status_code=415, detail="不支持的文件格式")


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
