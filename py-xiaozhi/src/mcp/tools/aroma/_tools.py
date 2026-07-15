"""香薰系统 MCP 工具注册。"""

import json
from typing import Any

from src.mcp.decorators import Prop, PropType, mcp_tool

from .manager import get_aroma_manager


@mcp_tool(
    name="aroma.enter",
    description=(
        "当用户说‘开启香薰系统’、‘进入香薰模式’或表达想配置香薰时调用。"
        "进入后请询问用户希望放松、专注、提神、助眠或其他场景；不要直接启动硬件。"
    ),
)
async def aroma_enter(args: dict[str, Any]) -> str:
    """进入香薰模式。"""
    return json.dumps(await get_aroma_manager().enter(), ensure_ascii=False)


@mcp_tool(
    name="aroma.start",
    description=(
        "仅在已进入香薰模式后调用：用户描述情绪、场景或想要的效果时，"
        "用 requirement 传递其原意并启动安全香薰配方。服务端理解用户需求后，应优先"
        "通过 recipe 传入 JSON 配方：{summary, stages:[{aromas:[香型名称], "
        "duration_seconds:正整数}]}。必须使所有阶段总时长恰好为 30 秒，优先只输出一个"
        "30 秒阶段，绝不可输出 1800 秒等长配方。香型名称必须存在于客户端映射；超长阶段"
        "会按本地单阶段上限自动连续拆分，方案总时长必须匹配本地配置目标。recipe 缺失或无效时"
        "客户端将从固定安全配方库中兜底选择。"
    ),
    props=[Prop("requirement", PropType.STR), Prop("recipe", PropType.STR, default="")],
)
async def aroma_start(args: dict[str, Any]) -> str:
    """启动香薰配方。"""
    return json.dumps(
        await get_aroma_manager().start(
            args.get("requirement", ""), server_recipe=args.get("recipe", "")
        ),
        ensure_ascii=False,
    )


@mcp_tool(
    name="aroma.status",
    description="当用户询问香薰是否正在运行、当前状态或当前通道时调用。",
)
async def aroma_status(args: dict[str, Any]) -> str:
    """查询香薰状态。"""
    return json.dumps(await get_aroma_manager().status(), ensure_ascii=False)


@mcp_tool(
    name="aroma.exit",
    description=(
        "当用户说‘停止香薰’、‘退出香薰系统’、‘关闭香薰模式’时必须调用。"
        "它会立即中止任务、关闭所有通道并恢复正常聊天。"
    ),
)
async def aroma_exit(args: dict[str, Any]) -> str:
    """停止香薰并退出模式。"""
    return json.dumps(await get_aroma_manager().exit(), ensure_ascii=False)
