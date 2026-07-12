"""DAM1600C 兼容继电器驱动。"""

import time
from collections.abc import Callable
from dataclasses import dataclass
from threading import Event


@dataclass(frozen=True)
class RelaySettings:
    """继电器连接和安全参数。"""

    port: str
    baudrate: int
    device_address: int
    timeout: float
    retries: int
    active_high: bool


class Dam1600CRelayDriver:
    """以 Modbus RTU 单线圈写入协议控制 DAM1600C 兼容板。"""

    def __init__(self, settings: RelaySettings):
        self._settings = settings

    def run_recipe(
        self,
        stages: list[dict],
        stop_event: Event,
        on_stage: Callable[[dict], None],
        on_started: Callable[[], None],
        on_error: Callable[[Exception], None],
    ) -> None:
        """在工作线程中执行配方，并在所有退出路径关闭全部通道。"""
        serial_port = None
        started = False
        try:
            serial_port = self._open_serial()
            for stage in stages:
                if stop_event.is_set():
                    break
                channels = stage["channel_numbers"]
                self._set_channels(serial_port, channels, enabled=True)
                on_stage(stage)
                if not started:
                    started = True
                    on_started()
                if stop_event.wait(stage["duration_seconds"]):
                    break
                self._set_channels(serial_port, channels, enabled=False)
        except Exception as error:
            if not started:
                on_error(error)
            raise
        finally:
            if serial_port is not None:
                try:
                    self._set_channels(serial_port, range(1, 17), enabled=False)
                except Exception:
                    pass
                try:
                    serial_port.close()
                except Exception:
                    pass

    def _open_serial(self):
        if not self._settings.port:
            raise RuntimeError("未配置香薰继电器串口")
        try:
            import serial
        except ImportError as error:
            raise RuntimeError("缺少 pyserial，无法控制香薰硬件") from error

        return serial.Serial(
            port=self._settings.port,
            baudrate=self._settings.baudrate,
            timeout=self._settings.timeout,
            write_timeout=self._settings.timeout,
        )

    def _set_channels(self, serial_port, channels, *, enabled: bool) -> None:
        for channel in channels:
            self._write_coil(serial_port, int(channel), enabled=enabled)

    def _write_coil(self, serial_port, channel: int, *, enabled: bool) -> None:
        if not 1 <= channel <= 16:
            raise ValueError(f"香薰通道必须在 1 到 16 之间，当前为 {channel}")

        coil_value = enabled == self._settings.active_high
        payload = bytes(
            [
                self._settings.device_address,
                0x05,
                0x00,
                channel - 1,
                0xFF if coil_value else 0x00,
                0x00,
            ]
        )
        frame = payload + self._crc16(payload).to_bytes(2, byteorder="little")
        last_error = None
        for attempt in range(self._settings.retries + 1):
            try:
                serial_port.write(frame)
                serial_port.flush()
                return
            except Exception as error:
                last_error = error
                if attempt < self._settings.retries:
                    time.sleep(0.05)
        raise RuntimeError(f"继电器通道 {channel} 写入失败") from last_error

    @staticmethod
    def _crc16(payload: bytes) -> int:
        crc = 0xFFFF
        for byte in payload:
            crc ^= byte
            for _ in range(8):
                crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
        return crc
