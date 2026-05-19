"""garden_daily — 每天扫一次 harvest 过期 / handle / vase 枯萎，关键事件让叶瑄说话。"""

import logging
import random

from core.scheduler.loop import _is_ready, _mark, _pipeline_send, _char_name
from core.garden import manager as garden_manager

logger = logging.getLogger(__name__)

# 状态变更必执行；发言只有 30% 概率触发。
# 例外：ask / gift 是社交动作，必发（不过 sample）。
SAMPLE_TALK_PROB = 0.30


async def _check_garden_daily() -> None:
    if not _is_ready("garden_daily"):
        return
    _mark("garden_daily")

    try:
        events = garden_manager.daily_check()
    except Exception:
        logger.exception("[garden] daily_check failed")
        return

    for event in events:
        await _emit(event)


async def _emit(event: dict) -> None:
    etype = event["type"]
    name = event.get("name", "?")
    char = _char_name()

    if etype == "harvest_expired":
        if random.random() < SAMPLE_TALK_PROB:
            if not _is_ready("garden_harvest_expired"):
                return
            await _pipeline_send(
                f"（{char}发现那株{name}放太久枯掉了，悄悄处理掉了）",
                trigger_name="garden_harvest_expired",
            )
            _mark("garden_harvest_expired")
        return

    if etype == "vase_wilted":
        if random.random() < SAMPLE_TALK_PROB:
            if not _is_ready("garden_vase_wilted"):
                return
            await _pipeline_send(
                f"（花瓶里那株{name}枯掉了，{char}默默把它收了）",
                trigger_name="garden_vase_wilted",
            )
            _mark("garden_vase_wilted")
        return

    if etype == "harvest_handle":
        action = event.get("handle_action")
        # ask / gift 必发（社交动作，不过 sample）
        if action == "ask":
            if not _is_ready("garden_handle_ask"):
                return
            await _pipeline_send(
                f"（{char}捧着那株{name}，不确定该怎么办，想问问你）",
                trigger_name="garden_handle_ask",
            )
            _mark("garden_handle_ask")
            return
        if action == "gift":
            if not _is_ready("garden_handle_gift"):
                return
            language = event.get("language", "")
            tail = f"——{language}" if language else ""
            await _pipeline_send(
                f"（{char}想把那株{name}送给你{tail}）",
                trigger_name="garden_handle_gift",
            )
            _mark("garden_handle_gift")
            return
        # dry / vase / silent 走 sample
        if action in ("dry", "vase"):
            if random.random() < SAMPLE_TALK_PROB:
                if not _is_ready("garden_handle_self"):
                    return
                verb = "做成干花" if action == "dry" else "放进了花瓶"
                await _pipeline_send(
                    f"（{char}把那株{name}{verb}，没有特别说什么）",
                    trigger_name="garden_handle_self",
                )
                _mark("garden_handle_self")
        # action == "silent"：什么都不做
