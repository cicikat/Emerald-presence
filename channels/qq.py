"""
channels/qq — QQ通道，通过NapCat发消息。
qq.enabled=false 或 standalone_mode=true 时不加载此通道。
"""

from channels.base import BaseChannel
import logging

logger = logging.getLogger(__name__)


class QQChannel(BaseChannel):
    def __init__(self, user_id: str):
        self._user_id = user_id
        self._active = True

    @property
    def name(self) -> str:
        return "qq"

    @property
    def is_active(self) -> bool:
        return self._active

    def set_active(self, active: bool) -> None:
        self._active = active

    async def send(self, content: str, user_id: str, behavior: dict | None = None) -> None:
        try:
            from core import qq_adapter
            await qq_adapter.send_message(user_id, content, is_group=False)
        except Exception as e:
            logger.warning(f"[qq_channel] 发送失败: {e}")
