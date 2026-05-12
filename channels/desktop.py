"""
channels/desktop — 桌宠通道，通过HTTP队列文件通知桌宠端。
桌宠端轮询data/channel_queue.json，有消息就显示气泡。
"""

import asyncio
import json
import time
import logging
from pathlib import Path

from channels.base import BaseChannel
from core.sandbox import get_paths

logger = logging.getLogger(__name__)

_queue_lock = asyncio.Lock()


class DesktopChannel(BaseChannel):
    def __init__(self):
        self._active = False  # 默认不活跃，桌宠连接时激活

    @property
    def name(self) -> str:
        return "desktop"

    @property
    def is_active(self) -> bool:
        return self._active

    def set_active(self, active: bool) -> None:
        self._active = active
        logger.info(f"[desktop_channel] 活跃状态: {active}")

    async def send(self, content: str, user_id: str) -> None:
        try:
            async with _queue_lock:
                q_file = get_paths().channel_queue()
                q_file.parent.mkdir(parents=True, exist_ok=True)
                queue = []
                if q_file.exists():
                    queue = json.loads(q_file.read_text(encoding="utf-8"))
                queue.append({
                    "content": content,
                    "timestamp": time.time(),
                })
                q_file.write_text(
                    json.dumps(queue, ensure_ascii=False), encoding="utf-8"
                )
        except Exception as e:
            logger.warning(f"[desktop_channel] 写入队列失败: {e}")
