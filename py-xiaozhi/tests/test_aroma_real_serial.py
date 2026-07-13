"""可选的真实 DAM1600C 串口冒烟测试。

默认跳过，避免测试过程误触真实负载。执行前必须断开香薰负载并显式设置环境变量。
"""

import os

import pytest

from src.mcp.tools.aroma.driver import Dam1600CRelayDriver, RelaySettings


@pytest.mark.hardware
def test_dam1600c_real_serial_all_channels_off():
    if os.getenv("AROMA_REAL_SERIAL_TEST") != "1":
        pytest.skip("设置 AROMA_REAL_SERIAL_TEST=1 才执行真实串口测试")
    port = os.getenv("AROMA_REAL_SERIAL_PORT")
    if not port:
        pytest.skip("未设置 AROMA_REAL_SERIAL_PORT")

    driver = Dam1600CRelayDriver(
        RelaySettings(
            port=port,
            baudrate=int(os.getenv("AROMA_REAL_SERIAL_BAUDRATE", "9600")),
            device_address=int(os.getenv("AROMA_REAL_SERIAL_DEVICE_ADDRESS", "1")),
            timeout=float(os.getenv("AROMA_REAL_SERIAL_TIMEOUT", "1")),
            retries=1,
            active_high=True,
        )
    )
    serial_port = driver._open_serial()
    try:
        driver._shutdown_all_channels(serial_port)
    finally:
        serial_port.close()
