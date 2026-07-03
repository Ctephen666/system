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
            if self._ctx.is_speaking():
                action = "当前正在说话，执行打断"
                await self._publish_wake_word_info(wake_word, full_text, state, action)
                await self._cmd.abort_speaking(AbortReason.WAKE_WORD_DETECTED)
                if self._audio_plugin and self._audio_plugin.codec:
                    await self._audio_plugin.codec.clear_audio_queue()
            else:
                action = "播放唤醒反馈并进入监听"
                await self._publish_wake_word_info(wake_word, full_text, state, action)

                # 服务端 TTS 需要先建立协议通道，音色由服务端/后台配置决定。
                connected = await self._cmd.connect_protocol()
                if not connected:
                    return
                await self._show_wake_ack(connected=connected)

                # 启动自动对话
                from src.constants.constants import ListeningMode

                mode = (
                    ListeningMode.REALTIME
                    if self._ctx.get_config().get_config("AEC_OPTIONS.ENABLED", True)
                    else ListeningMode.AUTO_STOP
                )
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
                "检测成功",
                唤醒词=info["wake_word"],
                原始结果=info["full_text"],
                当前状态=info["device_state"],
                后续动作=info["action"],
                时间=info["timestamp"],
            )
        )

    async def _show_wake_ack(self, connected: bool = False) -> None:
        """
        播放/显示唤醒反馈。

        默认走服务端 TTS，使音色与用户在服务端/后台配置保持一致。
        本地 TTS 只作为显式配置的 fallback，不阻塞后续监听流程。
        """
        config = self._ctx.get_config()
        ack_text = config.get_config(
            "WAKE_WORD_OPTIONS.WAKE_RESPONSE_TEXT", "我在我在"
        )
        if not ack_text:
            return

        logger.info(_wake_log("唤醒反馈", 内容=ack_text))
        tts_enabled = config.get_config(
            "WAKE_WORD_OPTIONS.WAKE_RESPONSE_TTS_ENABLED", True
        )
        tts_mode = str(
            config.get_config("WAKE_WORD_OPTIONS.WAKE_RESPONSE_TTS_MODE", "server")
        ).lower()
        if tts_mode != "server":
            logger.warning(
                _wake_log("唤醒反馈配置调整", 原模式=tts_mode, 新模式="server", 原因="要求音色与对话一致")
            )
            tts_mode = "server"
        tts_timeout = float(
            config.get_config("WAKE_WORD_OPTIONS.WAKE_RESPONSE_TTS_TIMEOUT", 8.0)
        )
        configured_fallback = config.get_config(
            "WAKE_WORD_OPTIONS.WAKE_RESPONSE_TTS_LOCAL_FALLBACK", True
        )
        if not configured_fallback:
            logger.warning(_wake_log("唤醒反馈配置调整", 配置项="本地兜底", 新值=True, 原因="避免服务端不支持 tts/speak 时静默"))
        local_fallback = True

        if tts_enabled and tts_mode == "server":
            if connected:
                await self._send_server_wake_ack_and_wait(
                    ack_text, tts_timeout, local_fallback
                )
            else:
                logger.warning(_wake_log("唤醒反馈失败", 模式="server", 原因="协议未连接"))
                if local_fallback:
                    await self._play_local_wake_ack_and_wait(ack_text)
        elif tts_enabled and tts_mode == "local":
            self._start_local_wake_ack(ack_text)

        try:
            from src.core.event_bus import Events

            await self._ctx.event_bus.emit(Events.UI_UPDATE_TEXT, ack_text)
        except Exception as e:
            logger.debug(_wake_log("UI提示失败", 错误=e))

    async def _send_server_wake_ack_and_wait(
        self, ack_text: str, timeout: float, local_fallback: bool
    ) -> None:
        """
        Request server-side TTS for the wake acknowledgement and wait until it ends.

        Server-side TTS is the only path that uses the same voice as normal
        conversation. If the server does not return a tts stop event, continue
        after timeout to avoid blocking wake-up forever.
        """
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
            if state == "start" and not started.done():
                started.set_result(True)
            elif state == "stop":
                if not started.done():
                    started.set_result(True)
                if not stopped.done():
                    stopped.set_result(True)

        self._ctx.event_bus.on(Events.INCOMING_JSON, on_incoming_json)
        try:
            await self._cmd.send_tts_speak(ack_text)
            logger.info(_wake_log("唤醒反馈请求", 模式="server", 内容=ack_text, 协议="tts/speak"))

            try:
                await asyncio.wait_for(started, timeout=min(2.0, timeout))
                logger.info(_wake_log("唤醒反馈开始", 模式="server"))
            except asyncio.TimeoutError:
                logger.warning(_wake_log("唤醒反馈未开始", 模式="server", 原因="未收到 TTS start", 推断="服务端可能不支持 tts/speak"))
                if local_fallback:
                    logger.warning(_wake_log("唤醒反馈兜底", 模式="local", 原因="server 未开始"))
                    await self._play_local_wake_ack_and_wait(ack_text)
                return

            try:
                await asyncio.wait_for(stopped, timeout=timeout)
                logger.info(_wake_log("唤醒反馈完成", 模式="server", 后续动作="进入监听"))
            except asyncio.TimeoutError:
                logger.warning(
                    _wake_log("唤醒反馈结束等待超时", 模式="server", 超时=f"{timeout}s", 后续动作="进入监听")
                )
        except Exception as e:
            logger.warning(_wake_log("唤醒反馈请求失败", 模式="server", 错误=e))
        finally:
            self._ctx.event_bus.off(Events.INCOMING_JSON, on_incoming_json)

    async def _play_local_wake_ack_and_wait(self, ack_text: str) -> None:
        started = self._start_local_wake_ack(ack_text)
        if started:
            wait_seconds = min(3.0, max(0.8, len(ack_text) * 0.25))
            logger.info(_wake_log("唤醒反馈等待", 模式="local", 估算时长=f"{wait_seconds:.1f}s"))
            await asyncio.sleep(wait_seconds)

    def _start_local_wake_ack(self, ack_text: str) -> bool:
        """Start non-blocking local TTS for the wake acknowledgement."""
        try:
            from src.utils.wake_ack_tts import speak_wake_ack

            if speak_wake_ack(ack_text):
                logger.info(_wake_log("唤醒反馈开始", 模式="local", 内容=ack_text))
                return True

            logger.info(_wake_log("唤醒反馈未开始", 模式="local", 原因="本地 TTS 未启动", 后续动作="仅显示 UI"))
            return False
        except Exception as e:
            logger.warning(_wake_log("唤醒反馈异常", 模式="local", 错误=e))
            return False

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
