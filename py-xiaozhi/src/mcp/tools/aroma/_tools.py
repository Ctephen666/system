"""香薰系统 MCP 工具注册。"""

import json
from typing import Any

from src.mcp.decorators import Prop, PropType, mcp_tool
from src.utils.config_manager import ConfigManager

from .manager import get_aroma_manager


AROMA_CATALOG: dict[str, tuple[str, str]] = {
    "lavender": ("薰衣草", "放松、助眠"),
    "bergamot": ("佛手柑", "舒缓情绪"),
    "rosemary": ("迷迭香", "清醒、专注"),
    "lemon": ("柠檬", "清新、提神"),
    "peppermint": ("薄荷", "提神醒脑"),
    "chamomile": ("洋甘菊", "安抚、助眠"),
    "cedarwood": ("雪松", "沉静、稳定"),
    "eucalyptus": ("尤加利", "清爽、舒畅"),
    "jasmine": ("茉莉", "舒缓、愉悦"),
    "rose": ("玫瑰", "放松、愉悦"),
    "sandalwood": ("檀香", "安定、冥想"),
    "ylang_ylang": ("依兰", "舒缓压力"),
    "tea_tree": ("茶树", "清新、净味"),
    "orange": ("甜橙", "愉悦、提振"),
    "frankincense": ("乳香", "沉静、冥想"),
    "vanilla": ("香草", "温暖、放松"),
}


def _build_aroma_start_description(channel_map: dict[str, Any]) -> str:
    """按当前通道映射构造供小智服务端使用的工具描述。"""
    channels: list[tuple[int, str]] = []
    for raw_name, raw_channel in channel_map.items():
        try:
            channel = int(raw_channel)
        except (TypeError, ValueError):
            continue
        if 1 <= channel <= 16:
            channels.append((channel, str(raw_name).strip().lower()))
    channels.sort()

    channel_lines = []
    for channel, name in channels:
        chinese_name, purpose = AROMA_CATALOG.get(name, (name, "按用户需求使用"))
        channel_lines.append(
            f"通道 {channel}：{chinese_name}（{name}；{purpose}）"
        )
    available_channels = "\n".join(channel_lines) or "当前未配置可用香型。"
    return (
        "仅在已进入香薰模式后调用。用 requirement 传递用户原意；"
        "必须优先通过 recipe 传入 JSON 配方："
        '{"summary":"简短中文摘要","stages":[{"aromas":["香型名称"],'
        '"duration_seconds":30}]}。所有阶段总时长必须恰好为 30 秒，'
        "优先只输出一个 30 秒阶段，绝不可输出 1800 秒等长配方。"
        "只能使用下列当前客户端已配置的中文名或 canonical 名，不能编造其他香型；"
        "客户端会根据通道映射执行并校验方案：\n"
        f"{available_channels}\n"
        "recipe 缺失或无效时，客户端将从固定安全配方库中兜底选择。"
    )


def _aroma_start_description() -> str:
    """读取启动时配置的通道映射，避免在描述中暴露其他配置。"""
    channel_map = ConfigManager.get_instance().get_config("AROMA.CHANNEL_MAP", {})
    return _build_aroma_start_description(
        channel_map if isinstance(channel_map, dict) else {}
    )


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
    description=_aroma_start_description(),
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
