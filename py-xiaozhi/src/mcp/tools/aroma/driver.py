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

    _WRITE_SINGLE_COIL = 0x05
    _NORMAL_RESPONSE_LENGTH = 8
    _EXCEPTION_RESPONSE_LENGTH = 5
    _ALL_CHANNELS = range(1, 17)

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
        primary_error = None
        try:
            serial_port = self._open_serial()
            self._shutdown_all_channels(serial_port)
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
            primary_error = error
            if not started:
                on_error(error)
            raise
        finally:
            if serial_port is not None:
                shutdown_error = None
                try:
                    self._shutdown_all_channels(serial_port)
                except Exception as error:
                    shutdown_error = error
                finally:
                    try:
                        serial_port.close()
                    except Exception:
                        pass
                if primary_error is None and shutdown_error is not None:
                    raise RuntimeError("香薰继电器安全关断失败") from shutdown_error

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

    def _shutdown_all_channels(self, serial_port) -> None:
        """尽力关闭全部通道，即使个别通道失败也继续关断其余通道。"""
        errors = []
        for channel in self._ALL_CHANNELS:
            try:
                self._write_coil(serial_port, channel, enabled=False)
            except Exception as error:
                errors.append(f"{channel}: {error}")
        if errors:
            raise RuntimeError(f"继电器通道安全关断失败: {', '.join(errors)}")

    def _write_coil(self, serial_port, channel: int, *, enabled: bool) -> None:
        if not 1 <= channel <= 16:
            raise ValueError(f"香薰通道必须在 1 到 16 之间，当前为 {channel}")

        coil_value = enabled == self._settings.active_high
        payload = bytes(
            [
                self._settings.device_address,
                self._WRITE_SINGLE_COIL,
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
                self._clear_input_buffer(serial_port)
                written = serial_port.write(frame)
                if written is not None and written != len(frame):
                    raise RuntimeError(
                        f"继电器通道 {channel} 指令写入不完整: {written}/{len(frame)}"
                    )
                serial_port.flush()
                response = self._read_write_response(serial_port)
                self._validate_write_response(frame, response)
                return
            except Exception as error:
                last_error = error
                if attempt < self._settings.retries:
                    time.sleep(0.05)
        raise RuntimeError(f"继电器通道 {channel} 写入失败: {last_error}") from last_error

    @staticmethod
    def _clear_input_buffer(serial_port) -> None:
        reset_input_buffer = getattr(serial_port, "reset_input_buffer", None)
        if reset_input_buffer is not None:
            reset_input_buffer()

    def _read_write_response(self, serial_port) -> bytes:
        """读取单线圈写入回包，并识别 Modbus 异常响应。"""
        header = self._read_exact(serial_port, 2)
        if header[1] == self._WRITE_SINGLE_COIL | 0x80:
            response = header + self._read_exact(
                serial_port, self._EXCEPTION_RESPONSE_LENGTH - len(header)
            )
            self._validate_crc(response)
            raise RuntimeError(f"继电器返回 Modbus 异常码: {response[2]}")
        return header + self._read_exact(
            serial_port, self._NORMAL_RESPONSE_LENGTH - len(header)
        )

    @staticmethod
    def _read_exact(serial_port, size: int) -> bytes:
        response = bytearray()
        while len(response) < size:
            chunk = serial_port.read(size - len(response))
            if not chunk:
                break
            response.extend(chunk)
        if len(response) != size:
            raise RuntimeError(f"继电器回包不完整: {len(response)}/{size}")
        return bytes(response)

    def _validate_write_response(self, frame: bytes, response: bytes) -> None:
        """校验地址、功能码、线圈数据与 CRC 均和写入指令一致。"""
        if len(response) != self._NORMAL_RESPONSE_LENGTH:
            raise RuntimeError(f"继电器回包长度无效: {len(response)}")
        self._validate_crc(response)
        if response[0] != self._settings.device_address:
            raise RuntimeError(f"继电器回包地址不匹配: {response[0]}")
        if response[1] != self._WRITE_SINGLE_COIL:
            raise RuntimeError(f"继电器回包功能码不匹配: {response[1]}")
        if response[:6] != frame[:6]:
            raise RuntimeError("继电器回包线圈地址或状态不匹配")

    def _validate_crc(self, response: bytes) -> None:
        if len(response) < 3:
            raise RuntimeError("继电器回包长度无效")
        expected_crc = self._crc16(response[:-2]).to_bytes(2, byteorder="little")
        if response[-2:] != expected_crc:
            raise RuntimeError("继电器回包 CRC 校验失败")

    @staticmethod
    def _crc16(payload: bytes) -> int:
        crc = 0xFFFF
        for byte in payload:
            crc ^= byte
            for _ in range(8):
                crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
        return crc
