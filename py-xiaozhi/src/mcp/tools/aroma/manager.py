"""香薰对话会话和任务生命周期管理。"""

import asyncio
import threading
from typing import Any

from src.logging import get_logger
from src.utils.config_manager import ConfigManager

from .driver import Dam1600CRelayDriver, RelaySettings
from .planner import AromaPlanner, AromaRecipe

logger = get_logger()


class AromaManager:
    """管理单一香薰会话，确保停止、失败和退出均安全关断。"""

    def __init__(self, config: ConfigManager | None = None):
        self._config = config or ConfigManager.get_instance()
        self._planner = AromaPlanner(self._config)
        self._mode_active = False
        self._starting_session_id: int | None = None
        self._session_id = 0
        self._task: asyncio.Task | None = None
        self._stop_event: threading.Event | None = None
        self._active_channels: list[int] = []
        self._current_stage = 0
        self._recipe: AromaRecipe | None = None
        self._last_error = ""

    async def enter(self) -> dict[str, Any]:
        """进入香薰对话模式。"""
        self._session_id += 1
        self._starting_session_id = None
        self._mode_active = True
        return {
            "success": True,
            "mode_active": True,
            "message": "香薰系统已开启，请告诉我想放松、专注、提神或助眠等需求。",
            "next_action": "询问用户的情绪、场景或期望效果，再调用 aroma.start。",
        }

    async def start(self, requirement: str) -> dict[str, Any]:
        """生成并异步启动香薰配方。"""
        if not self._mode_active:
            return self._error("not_in_mode", "请先进入香薰系统，再描述您的需求。")
        if not isinstance(requirement, str) or not requirement.strip():
            return self._error("empty_requirement", "请告诉我您希望香薰带来的效果。")
        if self._is_busy():
            return self._error("already_running", "香薰任务正在运行，请先停止或退出香薰系统。")
        if not self._as_bool(self._config.get_config("AROMA.ENABLED", False), False):
            return self._error(
                "hardware_disabled",
                "香薰硬件控制未启用；请在本地配置中将 AROMA.ENABLED 设为 true。",
            )
        if not str(self._config.get_config("AROMA.SERIAL_PORT", "")).strip():
            return self._error(
                "hardware_unconfigured",
                "未配置香薰继电器串口；请设置 AROMA.SERIAL_PORT 后重试。",
            )

        session_id = self._session_id
        self._starting_session_id = session_id
        try:
            recipe = await self._planner.create_recipe(requirement.strip())
        except Exception as error:
            logger.error(f"[AromaManager] 配方生成失败: {error}", exc_info=True)
            self._clear_starting(session_id)
            return self._error("recipe_error", "无法生成安全的香薰配方，请检查通道映射。")
        if not self._mode_active or session_id != self._session_id:
            self._clear_starting(session_id)
            return self._error("mode_exited", "香薰模式已退出，未启动任何硬件。")

        self._recipe = recipe
        self._last_error = ""
        self._current_stage = 0
        self._stop_event = threading.Event()
        loop = asyncio.get_running_loop()
        startup = loop.create_future()
        stop_event = self._stop_event
        self._task = asyncio.create_task(
            self._run_recipe(recipe, startup, loop, stop_event), name="aroma:recipe"
        )
        self._clear_starting(session_id)
        task = self._task
        try:
            await asyncio.wait_for(
                asyncio.shield(startup), timeout=self._startup_timeout()
            )
        except asyncio.CancelledError:
            stop_event.set()
            raise
        except Exception as error:
            stop_event.set()
            if task is not None:
                await task
            logger.warning(f"[AromaManager] 香薰硬件未能启动: {error}")
            return self._error(
                "serial_error", "香薰硬件未能启动，请检查串口连接和继电器配置。"
            )

        return {
            "success": True,
            "running": True,
            "channels": self._active_channels,
            "pattern": recipe.stages[0]["pattern"],
            "total_duration_seconds": sum(
                stage["duration_seconds"] for stage in recipe.stages
            ),
            "recipe": recipe.summary,
            "source": recipe.source,
            "message": "香薰已启动；可询问状态，或说停止香薰、退出香薰系统。",
        }

    async def status(self) -> dict[str, Any]:
        """返回不会暴露凭据的当前香薰状态。"""
        return {
            "success": True,
            "mode_active": self._mode_active,
            "running": self._is_running(),
            "active_channels": self._active_channels,
            "current_stage": self._current_stage,
            "recipe": self._recipe.summary if self._recipe else None,
            "last_error": self._last_error or None,
        }

    async def exit(self) -> dict[str, Any]:
        """中止任务、关闭全部通道并退出香薰对话模式。"""
        self._mode_active = False
        self._session_id += 1
        self._starting_session_id = None
        task = self._task
        if self._stop_event is not None:
            self._stop_event.set()
        if task is not None:
            await task
        self._active_channels = []
        return {
            "success": True,
            "mode_active": False,
            "running": False,
            "message": "已关闭香薰输出并退出香薰系统，现在可以正常聊天。",
            "next_action": "恢复普通对话；除非用户再次明确要求，否则不要调用香薰工具。",
        }

    async def _run_recipe(
        self,
        recipe: AromaRecipe,
        startup: asyncio.Future[None],
        loop: asyncio.AbstractEventLoop,
        stop_event: threading.Event,
    ) -> None:
        try:
            await asyncio.to_thread(
                self._driver().run_recipe,
                recipe.stages,
                stop_event,
                lambda stage: loop.call_soon_threadsafe(self._set_stage, recipe, stage),
                lambda: loop.call_soon_threadsafe(self._resolve_startup, startup),
                lambda error: loop.call_soon_threadsafe(
                    self._reject_startup, startup, error
                ),
            )
        except asyncio.CancelledError:
            stop_event.set()
            raise
        except Exception as error:
            self._last_error = str(error)
            logger.error(f"[AromaManager] 香薰任务失败: {error}", exc_info=True)
            self._reject_startup(startup, error)
        finally:
            stop_event.set()
            if not startup.done():
                self._reject_startup(startup, RuntimeError("香薰任务在启动前已停止"))
            self._active_channels = []
            self._current_stage = 0
            if self._task is asyncio.current_task():
                self._task = None
                self._stop_event = None

    def _driver(self) -> Dam1600CRelayDriver:
        return Dam1600CRelayDriver(
            RelaySettings(
                port=str(self._config.get_config("AROMA.SERIAL_PORT", "")),
                baudrate=int(self._config.get_config("AROMA.BAUDRATE", 9600)),
                device_address=int(self._config.get_config("AROMA.DEVICE_ADDRESS", 1)),
                timeout=float(self._config.get_config("AROMA.SERIAL_TIMEOUT", 1.0)),
                retries=max(0, int(self._config.get_config("AROMA.RETRIES", 1))),
                active_high=self._as_bool(
                    self._config.get_config("AROMA.ACTIVE_HIGH", True), True
                ),
            )
        )

    def _set_stage(self, recipe: AromaRecipe, stage: dict) -> None:
        self._current_stage = recipe.stages.index(stage) + 1
        self._active_channels = list(stage["channel_numbers"])

    @staticmethod
    def _resolve_startup(startup) -> None:
        if not startup.done():
            startup.set_result(None)

    @staticmethod
    def _reject_startup(startup, error: Exception) -> None:
        if not startup.done():
            startup.set_exception(error)

    def _is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    def _is_busy(self) -> bool:
        return self._starting_session_id is not None or self._is_running()

    def _clear_starting(self, session_id: int) -> None:
        """只清理对应会话的规划标记，避免旧请求干扰新会话。"""
        if self._starting_session_id == session_id:
            self._starting_session_id = None

    def _startup_timeout(self) -> float:
        timeout = float(self._config.get_config("AROMA.SERIAL_TIMEOUT", 1.0))
        retries = max(0, int(self._config.get_config("AROMA.RETRIES", 1)))
        return max(2.0, timeout * (retries + 2) + 1.0)

    @staticmethod
    def _as_bool(value: Any, default: bool) -> bool:
        """只接受明确的布尔配置值，避免字符串 false 被误判为真。"""
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "yes", "on"}:
                return True
            if normalized in {"false", "0", "no", "off"}:
                return False
        return default

    @staticmethod
    def _error(code: str, message: str) -> dict[str, Any]:
        return {"success": False, "error": code, "message": message}


_manager: AromaManager | None = None


def get_aroma_manager() -> AromaManager:
    """获取共享的香薰会话管理器。"""
    global _manager
    if _manager is None:
        _manager = AromaManager()
    return _manager
