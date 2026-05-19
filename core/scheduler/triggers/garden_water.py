"""
garden_water trigger — 每 30 分钟 roll 一次自动浇水。
开花时让叶瑄说一句（低频里程碑，不 sample）。
"""

import logging

from core.scheduler.loop import _is_ready, _mark, _pipeline_send, _char_name
from core.garden import manager as garden_manager

logger = logging.getLogger(__name__)


async def _check_garden_water() -> None:
    if not _is_ready("garden_water"):
        return
    _mark("garden_water")

    try:
        result = garden_manager.auto_water_tick()
    except Exception:
        logger.exception("[garden] auto_water_tick failed")
        return

    if not result or not result.get("ok"):
        return

    # 浇水本身不发言；只在开花（里程碑）时说话
    for event in result.get("events", []):
        if event["type"] == "bloom":
            if not _is_ready("garden_bloom"):
                continue
            await _pipeline_send(
                f"（{_char_name()}发现花园里那株{event['name']}开了，站在那里看了一会儿）",
                trigger_name="garden_bloom",
            )
            _mark("garden_bloom")
