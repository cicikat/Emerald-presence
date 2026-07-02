"""channels/ui_push — 把交互式下行 fan 到所有已连的 UI 客户端（桌宠 + 设备）。"""

from channels import desktop_ws, device_ws


def any_connected() -> bool:
    return desktop_ws.is_connected() or device_ws.is_connected()


async def push_stream_start(msg_id, **kw):
    if desktop_ws.is_connected():
        await desktop_ws.push_stream_start(msg_id, **kw)
    if device_ws.is_connected():
        await device_ws.push_stream_start(msg_id, **kw)


async def push_stream_delta(msg_id, delta):
    if desktop_ws.is_connected():
        await desktop_ws.push_stream_delta(msg_id, delta)
    if device_ws.is_connected():
        await device_ws.push_stream_delta(msg_id, delta)


async def push_stream_end(msg_id):
    if desktop_ws.is_connected():
        await desktop_ws.push_stream_end(msg_id)
    if device_ws.is_connected():
        await device_ws.push_stream_end(msg_id)


async def push_segments(content, segments, **kw):
    if desktop_ws.is_connected():
        await desktop_ws.push_segments(content, segments, **kw)
    if device_ws.is_connected():
        await device_ws.push_segments(content, segments, **kw)
