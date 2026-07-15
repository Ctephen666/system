"""香薰配方验证和固定配方库。"""

import json
from dataclasses import dataclass
from typing import Any

from src.utils.config_manager import ConfigManager


_AROMA_NAME_ALIASES = {
    "薰衣草": "lavender",
    "佛手柑": "bergamot",
    "迷迭香": "rosemary",
    "柠檬": "lemon",
    "薄荷": "peppermint",
    "洋甘菊": "chamomile",
    "罗马洋甘菊": "chamomile",
    "雪松": "cedarwood",
    "尤加利": "eucalyptus",
    "茉莉": "jasmine",
    "玫瑰": "rose",
    "檀香": "sandalwood",
    "依兰": "ylang_ylang",
    "依兰依兰": "ylang_ylang",
    "茶树": "tea_tree",
    "甜橙": "orange",
    "橙子": "orange",
    "乳香": "frankincense",
    "香草": "vanilla",
}


@dataclass(frozen=True)
class AromaRecipe:
    """可安全执行的香薰配方。"""

    summary: str
    stages: list[dict[str, Any]]
    source: str


class AromaPlanner:
    """验证小智服务端配方，并在其不可用时选择固定配方。"""

    def __init__(self, config: ConfigManager):
        self._config = config

    async def create_recipe(
        self, requirement: str, server_recipe: str | dict[str, Any] | None = None
    ) -> AromaRecipe:
        """将服务端方案转换为继电器 pattern，或使用固定配方兜底。"""
        channel_map = self._channel_map()
        if not channel_map:
            raise RuntimeError("香薰通道映射为空，无法生成配方")
        recipe_data = self._parse_server_recipe(server_recipe)
        if recipe_data is not None:
            recipe = self._validate_server_recipe(recipe_data, channel_map)
            if recipe is not None:
                return recipe
        return self._fixed_library_recipe(requirement, channel_map)

    @staticmethod
    def _parse_server_recipe(
        server_recipe: str | dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if isinstance(server_recipe, dict):
            return server_recipe
        if not isinstance(server_recipe, str) or not server_recipe.strip():
            return None
        try:
            data = json.loads(server_recipe)
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, dict) else None

    def _validate_server_recipe(
        self, data: dict[str, Any], channel_map: dict[str, int]
    ) -> AromaRecipe | None:
        raw_stages = data.get("stages")
        if not isinstance(raw_stages, list) or not raw_stages:
            return None

        stages: list[dict[str, Any]] = []
        total_duration = 0
        for raw_stage in raw_stages:
            stage = self._validate_server_stage(raw_stage, channel_map)
            if stage is None:
                return None
            total_duration += stage["duration_seconds"]
            if total_duration > self._max_total_seconds():
                return None
            stages.extend(self._split_stage(stage))

        if total_duration != self._target_total_seconds():
            return None

        summary = data.get("summary", "个性化香薰方案")
        if not isinstance(summary, str):
            return None
        return AromaRecipe(
            summary=summary.strip()[:80] or "个性化香薰方案",
            stages=stages,
            source="xiaozhi_server",
        )

    def _validate_server_stage(
        self, raw_stage: Any, channel_map: dict[str, int]
    ) -> dict[str, Any] | None:
        if not isinstance(raw_stage, dict):
            return None
        raw_names = raw_stage.get("aromas")
        duration = raw_stage.get("duration_seconds")
        if (
            not isinstance(raw_names, list)
            or not raw_names
            or isinstance(duration, bool)
            or not isinstance(duration, int)
            or duration <= 0
        ):
            return None
        names: list[str] = []
        for raw_name in raw_names:
            if not isinstance(raw_name, str):
                return None
            normalized_name = raw_name.strip().lower()
            name = _AROMA_NAME_ALIASES.get(normalized_name, normalized_name)
            if not name or name not in channel_map or name in names:
                return None
            names.append(name)
        return self._stage_from_names(names, duration, channel_map)

    def _split_stage(self, stage: dict[str, Any]) -> list[dict[str, Any]]:
        """将超出单阶段时长限制的服务端阶段拆为连续阶段。"""
        duration = stage["duration_seconds"]
        stages = []
        while duration > 0:
            stage_duration = min(duration, self._max_stage_seconds())
            stages.append({**stage, "duration_seconds": stage_duration})
            duration -= stage_duration
        return stages

    def _fixed_library_recipe(
        self, requirement: str, channel_map: dict[str, int]
    ) -> AromaRecipe:
        text = requirement.lower()
        recipes = (
            (("睡", "失眠", "助眠"), ("lavender", "chamomile"), "舒缓助眠"),
            (("专注", "学习", "工作"), ("rosemary", "lemon"), "清醒专注"),
            (("提神", "困", "精神"), ("peppermint", "lemon"), "清新提神"),
        )
        names = ("lavender", "bergamot")
        summary = "放松舒缓"
        for keywords, candidate_names, candidate_summary in recipes:
            if any(keyword in text for keyword in keywords):
                names, summary = candidate_names, candidate_summary
                break
        available_names = [name for name in names if name in channel_map]
        if not available_names:
            available_names = [next(iter(channel_map))]
        stage = self._stage_from_names(
            available_names, self._target_total_seconds(), channel_map
        )
        return AromaRecipe(summary=summary, stages=[stage], source="fixed_library")

    def _stage_from_names(
        self, names: list[str], duration: int, channel_map: dict[str, int]
    ) -> dict[str, Any]:
        pattern = [0] * 16
        channel_numbers = [channel_map[name] for name in names]
        for channel_number in channel_numbers:
            pattern[channel_number - 1] = self._default_on_value()
        return {
            "pattern": pattern,
            "channel_names": names,
            "channel_numbers": channel_numbers,
            "duration_seconds": duration,
        }

    def _channel_map(self) -> dict[str, int]:
        raw_map = self._config.get_config("AROMA.CHANNEL_MAP", {})
        if not isinstance(raw_map, dict):
            return {}
        result = {}
        for name, channel in raw_map.items():
            try:
                channel_number = int(channel)
            except (TypeError, ValueError):
                continue
            if 1 <= channel_number <= 16:
                result[str(name).strip().lower()] = channel_number
        return result

    def _max_stage_seconds(self) -> int:
        configured = int(self._config.get_config("AROMA.MAX_STAGE_SECONDS", 600))
        return max(1, min(configured, 3600))

    def _max_total_seconds(self) -> int:
        configured = int(self._config.get_config("AROMA.MAX_TOTAL_SECONDS", 1800))
        return max(1, min(configured, 14400))

    def _target_total_seconds(self) -> int:
        configured = int(
            self._config.get_config(
                "AROMA.TOTAL_DURATION_SECONDS",
                30,
            )
        )
        return max(1, min(configured, self._max_total_seconds()))

    def _pattern_mode(self) -> str:
        mode = str(self._config.get_config("AROMA.PATTERN_MODE", "binary")).lower()
        return mode if mode in {"binary", "concentration"} else "binary"

    def _default_on_value(self) -> int:
        return (
            1
            if self._pattern_mode() == "binary"
            else int(self._config.get_config("AROMA.DEFAULT_CONCENTRATION", 100))
        )
