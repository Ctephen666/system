"""用户配置加载、合并与安全写入。"""

import json
import os
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any

from src.logging import get_logger
from src.utils.config_defaults import create_default_config
from src.utils.resource_finder import (
    get_config_dir,
    get_user_cache_dir,
    get_user_data_dir,
)

logger = get_logger()


class ConfigManager:
    """按环境变量、仓库和旧用户目录的优先级管理 JSON 配置。"""

    _instance = None
    CONFIG_PATH_ENV_VAR = "XIAOZHI_CONFIG_PATH"

    # 保留既有公开接口；内部始终通过 create_default_config() 获取独立副本。
    DEFAULT_CONFIG = create_default_config()

    def __new__(cls):
        """确保单例模式。"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """初始化配置管理器。"""
        if self._initialized:
            return
        self._initialized = True

        self._init_config_paths()
        self._ensure_required_directories()
        self._config = self._load_config()

    def _init_config_paths(self) -> None:
        """选择当前配置来源，并保留旧用户目录作为兼容回退。"""
        self.repository_config_file = get_config_dir() / "config.json"
        self.legacy_config_dir = get_user_data_dir() / "config"
        self.legacy_config_file = self.legacy_config_dir / "config.json"
        self._config_load_failed = False

        environment_path = os.environ.get(self.CONFIG_PATH_ENV_VAR)
        if environment_path:
            self._set_config_file(Path(environment_path).expanduser(), "environment")
        elif self.repository_config_file.exists():
            self._set_config_file(self.repository_config_file, "repository")
        elif self.legacy_config_file.exists():
            self._set_config_file(self.legacy_config_file, "legacy")
        else:
            self._set_config_file(self.repository_config_file, "repository")

        logger.info("配置来源: %s", self.config_source)
        logger.info("配置文件: %s", self.config_file.absolute())

    def _set_config_file(self, config_file: Path, source: str) -> None:
        """设置当前读取与写入的配置文件。"""
        self.config_file = config_file
        self.config_dir = config_file.parent
        self.config_source = source

    def _ensure_required_directories(self) -> None:
        """确保运行时缓存目录可用。"""
        cache_dir = get_user_cache_dir()
        logger.debug("缓存目录: %s", cache_dir.absolute())

    def _load_config(self) -> dict[str, Any]:
        """加载用户配置；格式错误时保留原文件并回退到内置默认值。"""
        self._config_load_failed = False
        if not self.config_file.exists():
            logger.info("配置文件不存在，本次运行使用内置默认配置")
            return create_default_config()

        try:
            logger.debug("找到配置文件: %s", self.config_file)
            custom_config = json.loads(self.config_file.read_text(encoding="utf-8"))
            if not isinstance(custom_config, dict):
                raise ValueError("配置根节点必须是 JSON 对象")
            return self._merge_configs(create_default_config(), custom_config)
        except json.JSONDecodeError as error:
            self._config_load_failed = True
            logger.error(
                "配置文件 JSON 格式错误，已保留原文件且未覆盖: %s（第 %s 行，第 %s 列）",
                self.config_file,
                error.lineno,
                error.colno,
            )
        except (OSError, UnicodeError, ValueError) as error:
            self._config_load_failed = True
            logger.error(
                "配置文件无法读取或格式无效，已保留原文件且未覆盖: %s（%s）",
                self.config_file,
                error,
            )
        except Exception as error:
            self._config_load_failed = True
            logger.error(
                "配置加载失败，已保留原文件且未覆盖: %s", self.config_file, exc_info=True
            )
            logger.debug("配置加载异常类型: %s", type(error).__name__)

        return create_default_config()

    def _save_config(self, config: dict[str, Any]) -> bool:
        """写回当前来源；仓库只读时安全回退到旧用户目录。"""
        if self._config_load_failed:
            logger.error("配置文件加载失败，拒绝覆盖原文件: %s", self.config_file)
            return False

        if self._write_config_file(config, self.config_file):
            return True

        if self.config_source == "repository":
            logger.warning("仓库配置不可写，回退到用户配置目录")
            if self._write_config_file(config, self.legacy_config_file):
                self._set_config_file(self.legacy_config_file, "legacy")
                return True

        return False

    def _write_config_file(self, config: dict[str, Any], config_file: Path) -> bool:
        """通过临时文件和原子替换写入指定配置文件。"""
        tmp_file = config_file.with_suffix(".tmp")
        try:
            config_file.parent.mkdir(parents=True, exist_ok=True)
            tmp_file.write_text(
                json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            os.replace(tmp_file, config_file)
            logger.debug("配置已保存到: %s", config_file)
            return True
        except Exception as error:
            logger.error("配置保存失败: %s", error, exc_info=True)
            try:
                tmp_file.unlink(missing_ok=True)
            except OSError:
                pass
            return False

    @staticmethod
    def _merge_configs(
        default: dict[str, Any], custom: dict[str, Any]
    ) -> dict[str, Any]:
        """递归合并配置，同时隔离默认值和用户配置中的可变对象。"""
        result = deepcopy(default)
        for key, value in custom.items():
            if isinstance(result.get(key), dict) and isinstance(value, dict):
                result[key] = ConfigManager._merge_configs(result[key], value)
            else:
                result[key] = deepcopy(value)
        return result

    def get_config(self, path: str, default: Any = None) -> Any:
        """按点分路径读取配置值。"""
        try:
            value = self._config
            for key in path.split("."):
                value = value[key]
            return value
        except (KeyError, TypeError):
            return default

    def update_config(self, path: str, value: Any) -> bool:
        """更新指定配置项并持久化到当前可写来源。"""
        try:
            if not path or any(not part for part in path.split(".")):
                raise ValueError("配置路径不能为空")

            updated_config = deepcopy(self._config)
            current = updated_config
            *parts, last = path.split(".")
            for part in parts:
                current = current.setdefault(part, {})
            current[last] = value
            if not self._save_config(updated_config):
                return False
            self._config = updated_config
            return True
        except (AttributeError, IndexError, TypeError, ValueError) as error:
            logger.error("配置更新错误 %s: %s", path, error, exc_info=True)
            return False

    def reload_config(self) -> bool:
        """重新加载配置文件。"""
        try:
            self._config = self._load_config()
            logger.info("配置文件已重新加载")
            return True
        except Exception as error:
            logger.error("配置重新加载失败: %s", error, exc_info=True)
            return False

    def generate_uuid(self) -> str:
        """生成 UUID v4。"""
        return str(uuid.uuid4())

    def initialize_client_id(self) -> None:
        """确保客户端 ID 已生成并持久化。"""
        if not self.get_config("SYSTEM_OPTIONS.CLIENT_ID"):
            client_id = self.generate_uuid()
            if self.update_config("SYSTEM_OPTIONS.CLIENT_ID", client_id):
                logger.info("已生成新的客户端 ID")
            else:
                logger.error("保存新的客户端 ID 失败")

    @classmethod
    def get_instance(cls):
        """获取配置管理器单例。"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
