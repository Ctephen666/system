"""配置默认值、模板和损坏配置保护的回归测试。"""

import json
from pathlib import Path

from src.utils.config_defaults import create_default_config
from src.utils.config_manager import ConfigManager


def test_default_config_factory_returns_independent_nested_values():
    first = create_default_config()
    second = create_default_config()

    first["AROMA"]["QWEN"]["MODEL"] = "changed-model"

    assert second["AROMA"]["QWEN"]["MODEL"] == "qwen3.6-plus"
    assert ConfigManager.DEFAULT_CONFIG["AROMA"]["QWEN"]["MODEL"] == "qwen3.6-plus"


def test_config_example_matches_complete_default_config():
    template_file = Path(__file__).parents[1] / "config" / "config.json"

    assert json.loads(template_file.read_text(encoding="utf-8")) == create_default_config()


def test_invalid_json_is_preserved_and_does_not_log_contents(tmp_path, caplog):
    invalid_config = '{"API_KEY": "TOP_SECRET",'
    config_file = tmp_path / "config.json"
    config_file.write_text(invalid_config, encoding="utf-8")

    manager = object.__new__(ConfigManager)
    manager.config_dir = tmp_path
    manager.config_file = config_file
    manager.config_source = "environment"
    manager._config_load_failed = False

    with caplog.at_level("ERROR"):
        loaded = manager._load_config()

    assert config_file.read_text(encoding="utf-8") == invalid_config
    assert loaded == create_default_config()
    assert "JSON 格式错误" in caplog.text
    assert "TOP_SECRET" not in caplog.text


def test_config_path_prefers_environment_then_repository_then_legacy(
    tmp_path, monkeypatch
):
    repository_dir = tmp_path / "repository" / "config"
    repository_dir.mkdir(parents=True)
    repository_file = repository_dir / "config.json"
    repository_file.write_text('{"LOGGING": {"LEVEL": "WARNING"}}', encoding="utf-8")

    legacy_dir = tmp_path / "legacy" / "config"
    legacy_dir.mkdir(parents=True)
    legacy_file = legacy_dir / "config.json"
    legacy_file.write_text('{"LOGGING": {"LEVEL": "ERROR"}}', encoding="utf-8")

    environment_file = tmp_path / "environment.json"
    environment_file.write_text('{"LOGGING": {"LEVEL": "DEBUG"}}', encoding="utf-8")

    monkeypatch.setattr(
        "src.utils.config_manager.get_config_dir", lambda: repository_dir
    )
    monkeypatch.setattr(
        "src.utils.config_manager.get_user_data_dir", lambda: legacy_dir.parent
    )
    monkeypatch.setenv(ConfigManager.CONFIG_PATH_ENV_VAR, str(environment_file))

    manager = object.__new__(ConfigManager)
    manager._init_config_paths()
    assert manager.config_file == environment_file
    assert manager.config_source == "environment"

    monkeypatch.delenv(ConfigManager.CONFIG_PATH_ENV_VAR)
    manager = object.__new__(ConfigManager)
    manager._init_config_paths()
    assert manager.config_file == repository_file
    assert manager.config_source == "repository"

    repository_file.unlink()
    manager = object.__new__(ConfigManager)
    manager._init_config_paths()
    assert manager.config_file == legacy_file
    assert manager.config_source == "legacy"


def test_repository_save_failure_falls_back_to_legacy_config(tmp_path):
    repository_file = tmp_path / "repository" / "config" / "config.json"
    legacy_file = tmp_path / "legacy" / "config" / "config.json"

    manager = object.__new__(ConfigManager)
    manager.config_file = repository_file
    manager.config_dir = repository_file.parent
    manager.config_source = "repository"
    manager.legacy_config_file = legacy_file
    manager._config_load_failed = False
    manager._config = create_default_config()

    def write_config(config, config_file):
        if config_file == repository_file:
            return False
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text(json.dumps(config), encoding="utf-8")
        return True

    manager._write_config_file = write_config

    assert manager.update_config("AROMA.ENABLED", True)
    assert manager.config_file == legacy_file
    assert json.loads(legacy_file.read_text(encoding="utf-8"))["AROMA"]["ENABLED"]


def test_repository_save_failure_keeps_source_when_legacy_fallback_fails(tmp_path):
    repository_file = tmp_path / "repository" / "config" / "config.json"
    legacy_file = tmp_path / "legacy" / "config" / "config.json"

    manager = object.__new__(ConfigManager)
    manager.config_file = repository_file
    manager.config_dir = repository_file.parent
    manager.config_source = "repository"
    manager.legacy_config_file = legacy_file
    manager._config_load_failed = False
    manager._config = create_default_config()
    manager._write_config_file = lambda config, config_file: False

    assert not manager.update_config("AROMA.ENABLED", True)
    assert manager.config_file == repository_file
    assert manager.config_source == "repository"
    assert not manager._config["AROMA"]["ENABLED"]


def test_invalid_config_is_not_overwritten_by_update(tmp_path):
    invalid_config = '{"API_KEY": "TOP_SECRET",'
    config_file = tmp_path / "config.json"
    config_file.write_text(invalid_config, encoding="utf-8")

    manager = object.__new__(ConfigManager)
    manager.config_dir = tmp_path
    manager.config_file = config_file
    manager.config_source = "environment"
    manager._config_load_failed = False
    manager._config = manager._load_config()

    assert not manager.update_config("AROMA.ENABLED", True)
    assert config_file.read_text(encoding="utf-8") == invalid_config
