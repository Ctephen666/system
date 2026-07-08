"""唤醒词插件.

检测唤醒词并触发对话。
"""

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from src.constants.constants import AbortReason, DeviceState
from src.logging import get_logger
from src.plugins.base import Plugin

if TYPE_CHECKING:
    from src.bootstrap.protocols import PluginCommands, PluginContext

logger = get_logger()


def _wake_log(event: str, **fields) -> str:
    parts = [f"事件={event}"]
    parts.extend(f"{key}={value}" for key, value in fields.items() if value is not None)
    return "[WakeWord] " + " | ".join(parts)


class WakeWordPlugin(Plugin):
    name = "wake_word"
    priority = 30
    requires = ["audio"]

    def __init__(self) -> None:
        super().__init__()
        self.detector = None
        self._wake_ack_waiting = False

    @property
    def _audio_plugin(self):
        """通过依赖注入获取 AudioPlugin."""
        return self.get_dep("audio")

    async def setup(self, ctx: "PluginContext", cmd: "PluginCommands") -> None:
        await super().setup(ctx, cmd)
        # 订阅配置变更事件（轻量，不加载模型）
        from src.core.event_bus import Events
        ctx.event_bus.on(Events.CONFIG_CHANGED, self._on_config_changed)

    async def _on_config_changed(self, data=None):
        """配置变更时重新加载唤醒词模型."""
        logger.info(_wake_log("配置变更", 动作="重新加载唤醒词模型"))
        try:
            self._ctx.get_config().reload_config()
        except Exception as e:
            logger.warning(_wake_log("配置重载失败", 错误=e))

        if not self.detector:
            logger.warning(_wake_log("模型热重载跳过", 原因="检测器未初始化", 后续动作="重启程序生效"))
            return

        if await self.reload_model():
            logger.info(_wake_log("模型热重载完成", 结果="成功"))
            return

        logger.warning(_wake_log("模型热重载失败", 后续动作="尝试恢复旧关键词文件"))
        if await self._restore_previous_keywords():
            logger.info(_wake_log("关键词恢复完成", 结果="已恢复旧文件并重新加载模型"))
        else:
            logger.warning(_wake_log("关键词恢复失败", 后续动作="重启程序生效"))

    async def _restore_previous_keywords(self) -> bool:
        """热重载失败时恢复上一次可用的 keywords.txt。"""
        try:
            import shutil

            from src.utils.config_manager import ConfigManager
            from src.utils.resource_finder import get_user_keywords_path

            lang = ConfigManager.get_instance().get_config(
                "WAKE_WORD_OPTIONS.WAKE_WORD_LANG", "zh"
            )
            keywords_path = get_user_keywords_path(lang)
            backup_path = keywords_path.with_suffix(keywords_path.suffix + ".bak")
            if not backup_path.exists():
                logger.warning(_wake_log("关键词恢复失败", 原因="未找到备份文件", 备份路径=backup_path))
                return False

            shutil.copy2(backup_path, keywords_path)
            logger.warning(_wake_log("关键词文件已恢复", 路径=keywords_path))
            return await self.reload_model()
        except Exception as e:
            logger.error(_wake_log("关键词恢复异常", 错误=e), exc_info=True)
            return False

    async def start(self) -> None:
        try:
            # 延迟加载模型到 start() 阶段，避免 setup() 时与 PortAudio DLL 冲突
            if self.detector is None:
                from src.audio_processing.wake_word_detect import WakeWordDetector

                self.detector = WakeWordDetector()
                if not await self.detector.initialize():
                    logger.info(_wake_log("检测器启动跳过", 原因="未启用或初始化失败"))
                    self.detector = None
                    return
                self.detector.on_detected(self._on_detected)
                self.detector.on_error = self._on_error

            if not self._audio_plugin or not self._audio_plugin.codec:
                logger.warning(_wake_log("检测器启动失败", 原因="未找到 audio_codec"))
                return
            await self.detector.start(self._audio_plugin.codec)
        except ImportError as e:
            logger.error(_wake_log("检测器导入失败", 错误=e))
            self.detector = None
        except Exception as e:
            logger.error(_wake_log("检测器启动异常", 错误=e), exc_info=True)

    async def stop(self) -> None:
        if self.detector:
            try:
                await self.detector.stop()
            except Exception as e:
                logger.warning(_wake_log("检测器停止失败", 错误=e))

    def register_resources(self, pool) -> None:
        detector = self.detector
        if detector:
            pool.register("wake_word.detector", detector.shutdown)

    async def reload_model(self, model_path: Optional[str] = None) -> bool:
        """热重载唤醒词模型.

        Args:
            model_path: 新模型路径（如 "models/en"）。如果为 None，从配置读取。

        Returns:
            是否重载成功
        """
        if not self.detector:
            logger.warning(_wake_log("模型热重载跳过", 原因="检测器未初始化"))
            return False

        try:
            return await self.detector.reload(model_path)
        except Exception as e:
            logger.error(_wake_log("模型热重载异常", 错误=e), exc_info=True)
            return False

    async def _on_detected(self, wake_word, full_text):
        """
        唤醒词检测回调.
        """
        try:
            state = self._ctx.get_device_state()
            logger.info(
                _wake_log(
                    "进入_on_detected",
                    wake_word=wake_word,
                    full_text=full_text,
                    state=self._format_state(state),
                )
            )
            if self._ctx.is_speaking():
                action = "当前正在说话，执行打断"
                await self._publish_wake_word_info(wake_word, full_text, state, action)
                await self._cmd.abort_speaking(AbortReason.WAKE_WORD_DETECTED)
                if self._audio_plugin and self._audio_plugin.codec:
                    await self._audio_plugin.codec.clear_audio_queue()
            else:
                action = "播放唤醒音频并进入监听"
                await self._publish_wake_word_info(wake_word, full_text, state, action)

                ack_config = self._get_wake_ack_config()
                logger.info(_wake_log("唤醒反馈模式", 模式=ack_config["mode"]))
                if not ack_config["enabled"]:
                    logger.info(_wake_log("唤醒反馈跳过", 原因="配置未启用"))
                elif ack_config["mode"] == "local_audio_file":
                    # await self._show_wake_ui_feedback(ack_config["text"])
                     await self._play_wake_ack_audio_file_and_wait(
                         ack_config["audio_path"],
                        ack_config["text"],
                     )

                logger.info(_wake_log("准备连接协议"))
                connected = await self._cmd.connect_protocol()
                logger.info(_wake_log("协议连接完成", opened=connected))
                if not connected:
                    return

                if ack_config["enabled"] and ack_config["mode"] == "remote_tts":
                    await self._send_remote_wake_ack_and_wait(
                        ack_config["text"],
                        ack_config["request_text"],
                        ack_config["start_timeout"],
                        ack_config["stop_timeout"],
                    )
                elif ack_config["enabled"] and ack_config["mode"] == "ui_only":
                    logger.info(_wake_log("准备发送 listen/detect", wake_word=wake_word))
                    await self._cmd.send_wake_word_detected(str(wake_word))
                    logger.info(_wake_log("listen/detect 已发送", 协议="listen/detect", 唤醒词=wake_word))
                    logger.info(_wake_log("唤醒上报已发送", 协议="listen/detect", 唤醒词=wake_word))
                    logger.warning(_wake_log("服务端不支持主动 TTS，已降级为 UI 提示"))
                    await self._show_wake_ui_feedback(ack_config["text"])

                # 启动自动对话
                from src.constants.constants import ListeningMode

                mode = (
                    ListeningMode.REALTIME
                    if self._ctx.get_config().get_config("AEC_OPTIONS.ENABLED", True)
                    else ListeningMode.AUTO_STOP
                )
                logger.info(_wake_log("进入监听", 模式=mode.value))
                await self._cmd.start_listening(mode)
        except Exception as e:
            logger.error(_wake_log("检测回调异常", 错误=e), exc_info=True)

    async def _publish_wake_word_info(self, wake_word, full_text, state, action: str):
        """
        统一记录并广播唤醒词识别信息，便于日志和 UI/调试面板复用。
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        state_name = self._format_state(state)
        payload = {
            "wake_word": str(wake_word),
            "full_text": str(full_text),
            "device_state": state_name,
            "action": action,
            "timestamp": timestamp,
        }

        self._log_wake_word_detected(payload)

        try:
            from src.core.event_bus import Events

            await self._ctx.event_bus.emit(Events.WAKE_WORD_DETECTED, payload)
        except Exception as e:
            logger.debug(_wake_log("事件广播失败", 错误=e))

    def _log_wake_word_detected(self, info: dict) -> None:
        """按固定格式输出唤醒词后台识别信息。"""
        logger.info(
            _wake_log(
                "唤醒词检测成功",
                唤醒词=info["wake_word"],
                原始结果=info["full_text"],
                当前状态=info["device_state"],
                后续动作=info["action"],
                时间=info["timestamp"],
            )
        )

    def _get_wake_ack_config(self) -> dict:
        config = self._ctx.get_config()
        enabled = bool(
            config.get_config(
                "WAKE_WORD_OPTIONS.WAKE_ACK_ENABLED",
                config.get_config("WAKE_WORD_OPTIONS.WAKE_RESPONSE_TTS_ENABLED", True),
            )
        )
        text = config.get_config(
            "WAKE_WORD_OPTIONS.WAKE_ACK_TEXT",
            config.get_config("WAKE_WORD_OPTIONS.WAKE_RESPONSE_TEXT", "老衲在此"),
        )
        migrated_old_ack_text = str(text).strip() == "我在我在"
        if migrated_old_ack_text:
            text = "老衲在此"
        mode = str(
            config.get_config(
                "WAKE_WORD_OPTIONS.WAKE_ACK_MODE",
                config.get_config("WAKE_WORD_OPTIONS.WAKE_RESPONSE_MODE", "remote_tts"),
            )
        ).lower()
        if mode in ("local_audio", "local_tts"):
            logger.warning(_wake_log("本地TTS方案已移除，唤醒反馈改用音频文件", 原模式=mode))
            mode = "local_audio_file"
        if mode in ("remote_tts", "server_tts"):
            logger.warning(_wake_log("唤醒反馈改用音频文件", 原模式=mode))
            mode = "local_audio_file"
        mode_map = {
            "local_audio_file": "local_audio_file",
            "audio_file": "local_audio_file",
            "server_tts": "remote_tts",
            "remote_tts": "remote_tts",
            "ui_only": "ui_only",
        }
        if mode not in mode_map:
            logger.warning(_wake_log("唤醒反馈模式无效", 配置值=mode, 降级="ui_only"))
            mode = "ui_only"

        start_timeout = float(
            config.get_config("WAKE_WORD_OPTIONS.WAKE_ACK_TTS_START_TIMEOUT", 5.0)
        )
        stop_timeout = float(
            config.get_config(
                "WAKE_WORD_OPTIONS.WAKE_ACK_TTS_STOP_TIMEOUT",
                config.get_config("WAKE_WORD_OPTIONS.WAKE_RESPONSE_TTS_TIMEOUT", 3.0),
            )
        )
        return {
            "enabled": enabled,
            "text": text,
            "request_text": self._get_wake_ack_request_text(str(text)),
            "audio_path": config.get_config(
                "WAKE_WORD_OPTIONS.WAKE_ACK_AUDIO_PATH",
                "老衲在此.wav",
            ),
            "mode": mode_map[mode],
            "start_timeout": min(max(start_timeout, 3.0), 8.0),
            "stop_timeout": min(max(stop_timeout, 8.0), 10.0),
        }

    def _get_wake_ack_request_text(self, ack_text: str) -> str:
        config = self._ctx.get_config()
        default_request = "请你只说老衲在此这四个字"
        request_text = config.get_config(
            "WAKE_WORD_OPTIONS.WAKE_ACK_REMOTE_REQUEST_TEXT",
            default_request,
        )
        if "我在我在" in str(request_text) or "老衲在此" in str(request_text):
            request_text = default_request
        return str(request_text or default_request)

    async def _show_wake_ui_feedback(self, ack_text: str) -> None:
        if not ack_text:
            return

        logger.info(_wake_log("UI反馈", 内容=ack_text))
        try:
            from src.core.event_bus import Events

            await self._ctx.event_bus.emit(Events.UI_UPDATE_TEXT, ack_text)
        except Exception as e:
            logger.debug(_wake_log("UI反馈失败", 错误=e))

    async def _play_wake_ack_audio_file_and_wait(
        self, audio_path_config: str, ack_text: str
    ) -> None:
        await self._show_wake_ui_feedback(ack_text)

        path = self._resolve_wake_ack_audio_path(audio_path_config)
        if not path:
            logger.warning(_wake_log("唤醒音频文件不存在", 配置=audio_path_config))
            return

        if not self._audio_plugin or not self._audio_plugin.codec:
            logger.warning(_wake_log("唤醒音频播放失败", 原因="audio_codec未初始化", 路径=path))
            return

        try:
            audio, sample_rate = await asyncio.to_thread(self._load_wav_as_output_pcm, path)
            duration = len(audio) / sample_rate if sample_rate else 0.0
            codec = self._audio_plugin.codec

            await codec.clear_audio_queue()
            logger.info(_wake_log("唤醒音频开始播放", 路径=path, 时长=f"{duration:.2f}s"))

            frame_size = max(1, int(sample_rate * 0.02))
            for start in range(0, len(audio), frame_size):
                await codec.write_pcm_direct(audio[start : start + frame_size])

            await asyncio.sleep(min(max(duration + 0.15, 0.3), 5.0))
            logger.info(_wake_log("唤醒音频播放完成", 路径=path))
        except Exception as e:
            logger.warning(_wake_log("唤醒音频播放异常", 路径=path, 错误=e), exc_info=True)
            await self._show_wake_ui_feedback(ack_text)

    def _resolve_wake_ack_audio_path(self, audio_path_config: str):
        from pathlib import Path

        from src.utils.resource_finder import get_assets_dir

        configured = Path(str(audio_path_config or "老衲在此.wav"))
        candidates = []
        if configured.is_absolute():
            candidates.append(configured)
        else:
            assets_dir = get_assets_dir()
            candidates.extend(
                [
                    assets_dir / configured,
                    assets_dir / configured.name,
                    assets_dir / "老衲在此.wav",
                    assets_dir / "老衲在此.WAV",
                ]
            )

        for candidate in candidates:
            if candidate.exists():
                return candidate

        assets_dir = get_assets_dir()
        stem = configured.stem.lower()
        for candidate in assets_dir.glob("*"):
            if candidate.is_file() and candidate.stem.lower() == stem and candidate.suffix.lower() == ".wav":
                return candidate

        return None

    def _load_wav_as_output_pcm(self, path):
        import wave

        import numpy as np
        import soxr

        from src.constants.constants import AudioConfig

        with wave.open(str(path), "rb") as wav_file:
            channels = wav_file.getnchannels()
            sample_rate = wav_file.getframerate()
            sample_width = wav_file.getsampwidth()
            frames = wav_file.readframes(wav_file.getnframes())

        if sample_width == 1:
            audio = (np.frombuffer(frames, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
        elif sample_width == 2:
            audio = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
        elif sample_width == 4:
            audio = np.frombuffer(frames, dtype="<i4").astype(np.float32) / 2147483648.0
        else:
            raise ValueError(f"Unsupported WAV sample width: {sample_width}")

        if channels > 1:
            audio = audio.reshape(-1, channels).mean(axis=1)

        target_rate = AudioConfig.OUTPUT_SAMPLE_RATE
        if sample_rate != target_rate:
            audio = soxr.resample(audio, sample_rate, target_rate).astype(np.float32)
            sample_rate = target_rate

        return audio.astype(np.float32), sample_rate

    async def _send_remote_wake_ack_and_wait(
        self,
        ack_text: str,
        request_text: str,
        start_timeout: float,
        stop_timeout: float,
    ) -> None:
        if not ack_text:
            return

        from src.core.event_bus import Events

        loop = asyncio.get_running_loop()
        started = loop.create_future()
        stopped = loop.create_future()

        async def on_incoming_json(message):
            if not isinstance(message, dict):
                return
            if message.get("type") != "tts":
                return

            state = message.get("state")
            if state in ("start", "sentence_start") and not started.done():
                logger.info(_wake_log("收到远程TTS开始", 内容=ack_text))
                started.set_result(True)
            elif state == "stop":
                if not started.done():
                    logger.info(_wake_log("收到远程TTS开始", 内容=ack_text))
                    started.set_result(True)
                if not stopped.done():
                    logger.info(_wake_log("收到远程TTS结束", 内容=ack_text))
                    stopped.set_result(True)

        self._ctx.event_bus.on(Events.INCOMING_JSON, on_incoming_json)
        self._wake_ack_waiting = True
        try:
            logger.info(
                _wake_log(
                    "准备发送远程TTS",
                    内容=ack_text,
                    协议="listen/detect",
                    请求文本=request_text,
                )
            )
            await self._cmd.send_tts_speak(request_text)
            logger.info(
                _wake_log(
                    "远程TTS请求已发送",
                    内容=ack_text,
                    协议="listen/detect",
                    请求文本=request_text,
                )
            )

            try:
                logger.info(_wake_log("等待远程TTS开始", 内容=ack_text, 超时=f"{start_timeout}s"))
                await asyncio.wait_for(started, timeout=start_timeout)
            except asyncio.TimeoutError:
                logger.warning(_wake_log("远程TTS未启动，降级为UI提示并进入监听"))
                await self._show_wake_ui_feedback(ack_text)
                return

            try:
                await asyncio.wait_for(stopped, timeout=stop_timeout)
            except asyncio.TimeoutError:
                logger.warning(
                    _wake_log("远程TTS结束等待超时", 内容=ack_text, 超时=f"{stop_timeout}s")
                )
        except Exception as e:
            logger.warning(_wake_log("远程TTS请求失败", 内容=ack_text, 错误=e))
            await self._show_wake_ui_feedback(ack_text)
        finally:
            self._wake_ack_waiting = False
            self._ctx.event_bus.off(Events.INCOMING_JSON, on_incoming_json)

    async def on_incoming_json(self, message) -> None:
        if isinstance(message, dict) and message.get("type") == "tts":
            logger.info(
                _wake_log(
                    "收到远程TTS事件",
                    state=message.get("state"),
                    当前是否唤醒反馈等待中=self._wake_ack_waiting,
                )
            )

    @staticmethod
    def _format_state(state) -> str:
        if isinstance(state, DeviceState):
            return state.name
        return getattr(state, "name", str(state).upper())

    async def _on_error(self, error):
        """
        唤醒词检测错误回调.
        """
        logger.error(_wake_log("检测器错误", 错误=error))
