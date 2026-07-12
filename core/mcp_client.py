"""
core/mcp_client.py — MCP (Model Context Protocol) 客户端（Brief 29 · 4）

只接外部工具，不接 resources/prompts、不接外部记忆库（见 cc-tasks/29 定位说明：
外接记忆绕过 prompt 层注入与固化链，会裂成两套真相；MCP 只用于外部工具）。

生命周期：main.py 启动时调 init_mcp_servers()，为每个已启用 server 建立 ClientSession、
list_tools，动态注册进 core.tool_dispatcher._TOOL_REGISTRY（name="mcp__{server}__{tool}"，
category="mcp"）。单 server 初始化失败只跳过该 server（log + 继续），不影响其他 server 与主流程。

工具只经 tool loop（Path C）暴露：角色卡 presence_ext.tool_categories 不含 "mcp" 就永远看不到
这些工具（探针 prompt 只拼 info/desktop，不覆盖 mcp 类），这就是"本我接 MCP、角色扮演不受影响"
的实现方式。

action_trace 落痕在 tool_dispatcher.execute() 的收口埋点自动生效，本模块不新增记账代码；
MCP 工具注册时不声明 trace_args，参数不落痕（防外部 server 的敏感入参入盘）。
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import AsyncExitStack
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_RESULT_CHAR_CAP = 2000

# server_name → handle；进程内单例，main.py 启动时填充，关闭时清空。
_servers: dict[str, "_ServerHandle"] = {}


@dataclass
class _ServerHandle:
    name: str
    cfg: dict
    stack: AsyncExitStack
    session: object  # mcp.ClientSession，延迟导入避免模块级依赖未安装时报错
    tool_names: list[str] = field(default_factory=list)


def _get_mcp_config() -> dict:
    from core.config_loader import get_config
    return get_config().get("mcp_servers", {}) or {}


async def init_mcp_servers() -> None:
    """启动时对每个已启用 server 建立 session + list_tools 并注册工具。

    单 server 失败隔离：某个 server 连不上只跳过它，log warning，不影响其他 server 或主流程。
    mcp_servers.enabled=false（默认）时整体跳过，零开销、零行为变化。
    """
    cfg = _get_mcp_config()
    if not cfg.get("enabled", False):
        return
    try:
        import mcp  # noqa: F401 — 依赖存在性检查，SDK 未安装时 fail-soft 跳过
    except ImportError:
        logger.warning("[mcp_client] mcp_servers.enabled=true 但未安装 mcp SDK（pip install mcp），跳过全部 MCP server")
        return

    servers = cfg.get("servers") or []
    for server_cfg in servers:
        name = server_cfg.get("name")
        if not name:
            logger.warning("[mcp_client] server 配置缺少 name，跳过: %s", server_cfg)
            continue
        try:
            await _connect_server(name, server_cfg)
        except Exception as e:
            logger.warning("[mcp_client] server '%s' 初始化失败，跳过（不影响其他 server）: %s", name, e)


async def _open_transport(stack: AsyncExitStack, server_cfg: dict):
    transport = server_cfg.get("transport", "stdio")
    if transport == "stdio":
        from mcp import StdioServerParameters
        from mcp.client.stdio import stdio_client
        command = server_cfg.get("command") or []
        if not command:
            raise ValueError("stdio transport 需要非空 command 数组")
        params = StdioServerParameters(command=command[0], args=list(command[1:]))
        read, write = await stack.enter_async_context(stdio_client(params))
        return read, write
    if transport == "http":
        from mcp.client.streamable_http import streamablehttp_client
        url = server_cfg.get("url")
        if not url:
            raise ValueError("http transport 需要 url")
        read, write, _get_session_id = await stack.enter_async_context(streamablehttp_client(url))
        return read, write
    raise ValueError(f"未知 transport: {transport!r}（只支持 stdio | http）")


async def _connect_server(name: str, server_cfg: dict) -> None:
    from mcp import ClientSession
    from core.tool_dispatcher import _TOOL_REGISTRY

    stack = AsyncExitStack()
    try:
        read, write = await _open_transport(stack, server_cfg)
        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        listed = await session.list_tools()
    except Exception:
        await stack.aclose()
        raise

    allow = set(server_cfg.get("allow_tools") or [])
    timeout_s = float(server_cfg.get("tool_timeout_s", 30))
    handle = _ServerHandle(name=name, cfg=server_cfg, stack=stack, session=session)

    for tool in listed.tools:
        if allow and tool.name not in allow:
            continue
        reg_name = f"mcp__{name}__{tool.name}"
        if reg_name in _TOOL_REGISTRY:
            logger.warning("[mcp_client] 工具名与已注册工具冲突，MCP 侧让位: %s", reg_name)
            continue
        _TOOL_REGISTRY[reg_name] = {
            "func": _make_tool_func(name, tool.name, timeout_s),
            "description": tool.description or "",
            "dangerous": False,
            "category": "mcp",
            "parameters": tool.inputSchema or {"type": "object", "properties": {}},
            "mcp_server": name,
            "mcp_tool": tool.name,
        }
        handle.tool_names.append(reg_name)

    _servers[name] = handle
    logger.info("[mcp_client] server '%s' 已连接，注册 %d 个工具", name, len(handle.tool_names))


def _make_tool_func(server_name: str, tool_name: str, timeout_s: float):
    async def _call(**kwargs) -> str:
        return await _call_tool(server_name, tool_name, kwargs, timeout_s)
    return _call


async def _call_tool(server_name: str, tool_name: str, arguments: dict, timeout_s: float) -> str:
    handle = _servers.get(server_name)
    if handle is None:
        raise RuntimeError(f"MCP server '{server_name}' 未连接")
    try:
        result = await asyncio.wait_for(
            handle.session.call_tool(tool_name, arguments), timeout=timeout_s
        )
    except Exception as e:
        logger.warning("[mcp_client] 调用 %s.%s 失败，尝试重连一次: %s", server_name, tool_name, e)
        await _reconnect_server(server_name)
        handle = _servers.get(server_name)
        if handle is None:
            raise
        result = await asyncio.wait_for(
            handle.session.call_tool(tool_name, arguments), timeout=timeout_s
        )
    return _format_result(result)


def _format_result(result) -> str:
    parts = []
    for item in getattr(result, "content", None) or []:
        text = getattr(item, "text", None)
        if text:
            parts.append(text)
    text = "\n".join(parts) if parts else "(无文本结果)"
    if len(text) > _RESULT_CHAR_CAP:
        text = text[:_RESULT_CHAR_CAP] + "…"
    if getattr(result, "isError", False):
        raise RuntimeError(f"MCP 工具返回错误: {text}")
    return text


async def _reconnect_server(name: str) -> None:
    """断线重连一次（不做后台心跳）：先摘除旧 handle 与其注册的工具条目，再重新连接。"""
    handle = _servers.pop(name, None)
    if handle is None:
        return
    from core.tool_dispatcher import _TOOL_REGISTRY
    for reg_name in handle.tool_names:
        _TOOL_REGISTRY.pop(reg_name, None)
    try:
        await handle.stack.aclose()
    except Exception:
        pass
    try:
        await _connect_server(name, handle.cfg)
    except Exception as e:
        logger.warning("[mcp_client] server '%s' 重连失败: %s", name, e)


async def shutdown_mcp_servers() -> None:
    """进程退出时清理全部 server session（main.py finally 块调用）。"""
    for name, handle in list(_servers.items()):
        try:
            await handle.stack.aclose()
        except Exception as e:
            logger.debug("[mcp_client] server '%s' 关闭时出错: %s", name, e)
    _servers.clear()
