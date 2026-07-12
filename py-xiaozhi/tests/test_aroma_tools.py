"""香薰 MCP 工具的离线测试。"""

import pytest

from src.mcp.decorators import iter_registered_mcp_tools
from src.mcp.tools.aroma.driver import Dam1600CRelayDriver, RelaySettings
from src.mcp.tools.aroma.manager import AromaManager
from src.mcp.tools.aroma.planner import AromaPlanner


class FakeConfig:
    """不读写本地配置文件的测试配置。"""

    def __init__(self, *, enabled: bool = False):
        self.values = {
            "AROMA.ENABLED": enabled,
            "AROMA.SERIAL_PORT": "COM_TEST",
            "AROMA.BAUDRATE": 9600,
            "AROMA.DEVICE_ADDRESS": 1,
            "AROMA.SERIAL_TIMEOUT": 0.01,
            "AROMA.RETRIES": 0,
            "AROMA.ACTIVE_HIGH": True,
            "AROMA.MAX_STAGE_SECONDS": 60,
            "AROMA.MAX_TOTAL_SECONDS": 120,
            "AROMA.CHANNEL_MAP": {"lavender": 1, "bergamot": 2},
            "AROMA.QWEN.API_KEY": "",
        }

    def get_config(self, path, default=None):
        return self.values.get(path, default)


class FakeDriver:
    """不访问真实串口的配方执行器。"""

    def run_recipe(self, stages, stop_event, on_stage, on_started, on_error):
        try:
            on_stage(stages[0])
            on_started()
            stop_event.wait(1)
        except Exception as error:
            on_error(error)
            raise


@pytest.mark.asyncio
async def test_enter_then_disabled_start_returns_json_error():
    manager = AromaManager(FakeConfig())

    entered = await manager.enter()
    result = await manager.start("我想放松")

    assert entered["mode_active"] is True
    assert result == {
        "success": False,
        "error": "hardware_disabled",
        "message": "香薰硬件控制未启用；请在本地配置中将 AROMA.ENABLED 设为 true。",
    }


@pytest.mark.asyncio
async def test_start_and_exit_interrupts_fake_recipe_without_serial_access():
    manager = AromaManager(FakeConfig(enabled=True))
    manager._driver = lambda: FakeDriver()
    await manager.enter()

    started = await manager.start("我想放松")
    exited = await manager.exit()

    assert started["success"] is True
    assert started["channels"] == [1, 2]
    assert exited["mode_active"] is False
    assert (await manager.status())["running"] is False


@pytest.mark.asyncio
async def test_local_recipe_is_used_without_qwen_key():
    recipe = await AromaPlanner(FakeConfig()).create_recipe("我需要助眠")

    assert recipe.source == "local_rule"
    assert recipe.stages[0]["channel_numbers"] == [1]


def test_dam1600c_uses_modbus_single_coil_frame():
    class FakeSerial:
        def __init__(self):
            self.frames = []

        def write(self, frame):
            self.frames.append(frame)

        def flush(self):
            return None

    driver = Dam1600CRelayDriver(
        RelaySettings("COM_TEST", 9600, 1, 0.1, 0, True)
    )
    serial_port = FakeSerial()
    driver._write_coil(serial_port, 1, enabled=True)

    frame = serial_port.frames[0]
    assert frame[:6] == bytes([1, 5, 0, 0, 0xFF, 0])
    assert frame[-2:] == Dam1600CRelayDriver._crc16(frame[:6]).to_bytes(2, "little")


def test_discovery_registers_all_aroma_tools():
    tool_names = {tool.name for tool in iter_registered_mcp_tools()}

    assert {"aroma.enter", "aroma.start", "aroma.status", "aroma.exit"} <= tool_names
