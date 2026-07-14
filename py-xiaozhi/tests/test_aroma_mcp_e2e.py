"""香薰 MCP JSON-RPC 端到端调用测试。"""

import json
import asyncio
from types import SimpleNamespace

import pytest

from src.mcp.decorators import iter_registered_mcp_tools
from src.mcp.mcp_server import McpServer


@pytest.mark.asyncio
async def test_aroma_mcp_json_rpc_enter_status_exit():
    """验证 MCP 请求能经过 tools/call 到达香薰工具并返回 JSON-RPC 响应。"""
    from src.mcp.tools.aroma import manager as manager_module

    manager_module._manager = None
    server = McpServer()
    server.tools = list(iter_registered_mcp_tools())
    replies = []

    async def capture(payload):
        replies.append(json.loads(payload))

    server.set_send_callback(capture)
    for request_id, tool_name, arguments in (
        (1, "aroma.enter", {}),
        (2, "aroma.status", {}),
        (3, "aroma.exit", {}),
    ):
        await server.parse_message(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": arguments},
            }
        )

    assert [reply["id"] for reply in replies] == [1, 2, 3]
    assert replies[0]["result"]["mode_active"] is True
    assert replies[1]["result"]["mode_active"] is True
    assert replies[2]["result"]["mode_active"] is False


@pytest.mark.asyncio
async def test_mcp_cancelled_notification_cancels_pending_tool():
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def slow_call(_arguments):
        started.set()
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    server = McpServer()
    server.tools = [SimpleNamespace(name="slow", call=slow_call)]
    server.set_send_callback(lambda _payload: asyncio.sleep(0))
    call_task = asyncio.create_task(
        server.parse_message(
            {
                "jsonrpc": "2.0",
                "id": 10,
                "method": "tools/call",
                "params": {"name": "slow", "arguments": {}},
            }
        )
    )
    await started.wait()
    await server.parse_message(
        {
            "jsonrpc": "2.0",
            "method": "notifications/cancelled",
            "id": "10",
            "params": {"reason": "test"},
        }
    )
    await call_task
    assert cancelled.is_set()
    assert not server._pending_calls
