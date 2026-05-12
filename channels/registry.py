"""
channels/registry — 通道注册表，管理所有活跃通道。
"""

import logging
from channels.base import BaseChannel

logger = logging.getLogger(__name__)

_channels: dict[str, BaseChannel] = {}


def register(channel: BaseChannel) -> None:
    """注册一个通道。"""
    _channels[channel.name] = channel
    logger.info(f"[channel_registry] 注册通道: {channel.name}")


def get(name: str) -> BaseChannel | None:
    return _channels.get(name)


def get_active() -> list[BaseChannel]:
    """返回所有活跃通道。"""
    return [c for c in _channels.values() if c.is_active]


async def broadcast(content: str, user_id: str) -> None:
    """广播到所有活跃通道。"""
    active = get_active()
    if not active:
        logger.warning("[channel_registry] 无活跃通道，消息丢弃")
        return
    for channel in active:
        await channel.send(content, user_id)
