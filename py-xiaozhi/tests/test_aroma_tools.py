"""香薰 MCP 工具的离线测试。"""

import asyncio
import sys
from threading import Event
from types import SimpleNamespace

import pytest

from src.mcp.decorators import iter_registered_mcp_tools
from src.mcp.tools.aroma.driver import Dam1600CRelayDriver, RelaySettings
from src.mcp.tools.aroma.manager import AromaManager
from src.mcp.tools.aroma.planner import AromaPlanner


class FakeSerial:
    """模拟串口的 Modbus 回显及可控异常回包。"""

    def __init__(self, response_factory=None):
        self.frames = []
        self.closed = False
        self._response_factory = response_factory or (lambda frame: frame)
        self._read_buffer = bytearray()

    def write(self, frame):
        self.frames.append(frame)
        self._read_buffer.extend(self._response_factory(frame))
        return len(frame)

    def flush(self):
        return None

    def read(self, size):
        chunk = bytes(self._read_buffer[:size])
        del self._read_buffer[:size]
        return chunk

    def reset_input_buffer(self):
        self._read_buffer.clear()

    def close(self):
        self.closed = True


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


class StopBeforeStartupDriver:
    """等待退出信号但不报告成功的驱动，用于启动握手回归测试。"""

    def run_recipe(self, stages, stop_event, on_stage, on_started, on_error):
        stop_event.wait(1)


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
async def test_string_false_does_not_enable_hardware():
    config = FakeConfig(enabled=True)
    config.values["AROMA.ENABLED"] = "false"
    manager = AromaManager(config)
    await manager.enter()

    result = await manager.start("我想放松")

    assert result["error"] == "hardware_disabled"


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
async def test_exit_during_startup_unblocks_start_without_starting_hardware():
    manager = AromaManager(FakeConfig(enabled=True))
    manager._driver = lambda: StopBeforeStartupDriver()
    await manager.enter()

    start_task = asyncio.create_task(manager.start("我想放松"))
    while manager._task is None:
        await asyncio.sleep(0)

    exited = await manager.exit()
    started = await start_task

    assert exited["success"] is True
    assert started["error"] == "serial_error"
    assert (await manager.status())["running"] is False


@pytest.mark.asyncio
async def test_local_recipe_is_used_without_qwen_key():
    recipe = await AromaPlanner(FakeConfig()).create_recipe("我需要助眠")

    assert recipe.source == "local_rule"
    assert recipe.stages[0]["channel_numbers"] == [1]
    assert len(recipe.stages[0]["pattern"]) == 16
    assert recipe.stages[0]["pattern"][0] == 1


def test_qwen_pattern_must_be_exactly_16_binary_values():
    planner = AromaPlanner(FakeConfig())
    assert planner._validate_pattern([0] * 15) is None
    assert planner._validate_pattern([0] * 15 + [2]) is None
    assert planner._validate_pattern([0] * 15 + [1]) == [0] * 15 + [1]


def test_concentration_pattern_accepts_0_to_100_only():
    config = FakeConfig()
    config.values["AROMA.PATTERN_MODE"] = "concentration"
    planner = AromaPlanner(config)
    assert planner._validate_pattern([100] * 16) == [100] * 16
    assert planner._validate_pattern([101] + [0] * 15) is None


def test_qwen_uses_bounded_openai_compatible_request(monkeypatch):
    config = FakeConfig()
    config.values.update(
        {
            "AROMA.QWEN.API_KEY": "test-secret",
            "AROMA.QWEN.BASE_URL": "https://example.invalid/compatible-mode/v1",
            "AROMA.QWEN.MODEL": "qwen3.6-plus",
        }
    )
    calls = {}

    class FakeCompletions:
        def create(self, **kwargs):
            calls["request"] = kwargs
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=(
                                '{"summary":"助眠","stages":['
                                '{"pattern":[1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],"duration_seconds":30}]}'
                            )
                        )
                    )
                ]
            )

    class FakeOpenAI:
        def __init__(self, **kwargs):
            calls["client"] = kwargs
            self._http_client = kwargs["http_client"]
            self.chat = SimpleNamespace(completions=FakeCompletions())

        def close(self):
            self._http_client.close()
            calls["closed"] = True

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))

    recipe = AromaPlanner(config)._create_qwen_recipe(
        "我需要助眠", {"lavender": 1, "bergamot": 2}
    )

    assert recipe["summary"] == "助眠"
    assert calls["client"]["api_key"] == "test-secret"
    assert calls["client"]["max_retries"] == 0
    assert calls["request"]["model"] == "qwen3.6-plus"
    assert calls["request"]["max_tokens"] == 600
    assert calls["closed"] is True
    assert (
        AromaPlanner._redact_error("failed test-secret", "test-secret")
        == "failed ***"
    )


def test_dam1600c_uses_modbus_single_coil_frame():
    driver = Dam1600CRelayDriver(
        RelaySettings("COM_TEST", 9600, 1, 0.1, 0, True)
    )
    serial_port = FakeSerial()
    driver._write_coil(serial_port, 1, enabled=True)

    frame = serial_port.frames[0]
    assert frame[:6] == bytes([1, 5, 0, 0, 0xFF, 0])
    assert frame[-2:] == Dam1600CRelayDriver._crc16(frame[:6]).to_bytes(2, "little")


@pytest.mark.parametrize(
    ("response_factory", "message"),
    [
        (lambda frame: frame[:-1] + bytes([frame[-1] ^ 0xFF]), "CRC"),
        (
            lambda frame: _replace_response_byte(frame, 0, 2),
            "地址不匹配",
        ),
        (
            lambda frame: _replace_response_byte(frame, 1, 0x06),
            "功能码不匹配",
        ),
        (
            lambda frame: _replace_response_byte(frame, 3, 1),
            "线圈地址或状态不匹配",
        ),
    ],
)
def test_dam1600c_rejects_invalid_write_responses(response_factory, message):
    driver = Dam1600CRelayDriver(
        RelaySettings("COM_TEST", 9600, 1, 0.1, 0, True)
    )

    with pytest.raises(RuntimeError, match=message):
        driver._write_coil(FakeSerial(response_factory), 1, enabled=True)


def _replace_response_byte(frame, index, value):
    response = bytearray(frame)
    response[index] = value
    response[-2:] = Dam1600CRelayDriver._crc16(response[:-2]).to_bytes(2, "little")
    return bytes(response)


def test_driver_closes_all_channels_when_stage_callback_fails():
    serial_port = FakeSerial()
    driver = Dam1600CRelayDriver(
        RelaySettings("COM_TEST", 9600, 1, 0.1, 0, True)
    )
    driver._open_serial = lambda: serial_port

    with pytest.raises(RuntimeError, match="stage callback failed"):
        driver.run_recipe(
            [{"channel_numbers": [1], "duration_seconds": 1}],
            Event(),
            lambda stage: (_ for _ in ()).throw(RuntimeError("stage callback failed")),
            lambda: None,
            lambda error: None,
        )

    assert serial_port.closed is True
    assert len(serial_port.frames) == 33
    assert all(frame[4:6] == bytes([0, 0]) for frame in serial_port.frames[:16])
    assert serial_port.frames[16][4:6] == bytes([0xFF, 0])
    assert all(frame[4:6] == bytes([0, 0]) for frame in serial_port.frames[17:])


def test_discovery_registers_all_aroma_tools():
    tool_names = {tool.name for tool in iter_registered_mcp_tools()}

    assert {"aroma.enter", "aroma.start", "aroma.status", "aroma.exit"} <= tool_names
