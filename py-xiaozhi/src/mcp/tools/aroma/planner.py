"""香薰配方规划器。"""

import asyncio
import json
from dataclasses import dataclass
from typing import Any

from src.logging import get_logger
from src.utils.config_manager import ConfigManager

logger = get_logger()


@dataclass(frozen=True)
class AromaRecipe:
    """可执行的香薰配方。"""

    summary: str
    stages: list[dict]
    source: str


class AromaPlanner:
    """优先使用 Qwen，失败时以本地规则生成安全配方。"""

    def __init__(self, config: ConfigManager):
        self._config = config

    async def create_recipe(self, requirement: str) -> AromaRecipe:
        """根据自然语言需求创建经过通道和时长校验的配方。"""
        channel_map = self._channel_map()
        ai_recipe = await asyncio.to_thread(
            self._create_qwen_recipe, requirement, channel_map
        )
        if ai_recipe is not None:
            validated = self._validate_recipe(ai_recipe, channel_map, "qwen")
            if validated is not None:
                return validated
        return self._local_recipe(requirement, channel_map)

    def _create_qwen_recipe(
        self, requirement: str, channel_map: dict[str, int]
    ) -> dict[str, Any] | None:
        api_key = self._config.get_config("AROMA.QWEN.API_KEY", "")
        if not api_key:
            return None
        try:
            import httpx
            from openai import OpenAI

            timeout = httpx.Timeout(
                connect=float(
                    self._config.get_config("AROMA.QWEN.CONNECT_TIMEOUT", 5.0)
                ),
                read=float(self._config.get_config("AROMA.QWEN.READ_TIMEOUT", 20.0)),
                write=float(self._config.get_config("AROMA.QWEN.READ_TIMEOUT", 20.0)),
                pool=float(self._config.get_config("AROMA.QWEN.CONNECT_TIMEOUT", 5.0)),
            )
            client = OpenAI(
                api_key=api_key,
                base_url=self._config.get_config("AROMA.QWEN.BASE_URL"),
                http_client=httpx.Client(timeout=timeout),
            )
            try:
                response = client.chat.completions.create(
                    model=self._config.get_config("AROMA.QWEN.MODEL", "qwen3.6-plus"),
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "你是香薰配方规划器。只返回 JSON 对象，格式为 "
                                '{"summary":"简短中文摘要","stages":['
                                '{"channels":["香型键名"],"duration_seconds":整数}]}'
                                f"。可用香型键名：{', '.join(channel_map)}。"
                                "每阶段 1 到 3 种香型，时长不超过 600 秒。"
                            ),
                        },
                        {"role": "user", "content": requirement},
                    ],
                    temperature=0.2,
                )
                content = response.choices[0].message.content or ""
            finally:
                client.close()
            return self._parse_json(content)
        except Exception as error:
            logger.warning(f"[AromaPlanner] Qwen 配方生成失败，改用本地规则: {error}")
            return None

    @staticmethod
    def _parse_json(content: str) -> dict[str, Any] | None:
        start = content.find("{")
        end = content.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            data = json.loads(content[start : end + 1])
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, dict) else None

    def _local_recipe(
        self, requirement: str, channel_map: dict[str, int]
    ) -> AromaRecipe:
        text = requirement.lower()
        rules = [
            (["睡", "失眠", "助眠"], ["lavender", "chamomile"], "舒缓助眠"),
            (["专注", "学习", "工作"], ["rosemary", "lemon"], "清醒专注"),
            (["提神", "困", "精神"], ["peppermint", "lemon"], "清新提神"),
        ]
        channel_names = ["lavender", "bergamot"]
        summary = "放松舒缓"
        for keywords, names, rule_summary in rules:
            if any(keyword in text for keyword in keywords):
                channel_names, summary = names, rule_summary
                break
        available_names = [name for name in channel_names if name in channel_map]
        if not available_names:
            available_names = list(channel_map)[:1]
        if not available_names:
            raise RuntimeError("香薰通道映射为空，无法生成配方")
        stage = {
            "channel_names": available_names[:3],
            "channel_numbers": [channel_map[name] for name in available_names[:3]],
            "duration_seconds": min(300, self._max_stage_seconds()),
        }
        return AromaRecipe(summary=summary, stages=[stage], source="local_rule")

    def _validate_recipe(
        self, data: dict[str, Any], channel_map: dict[str, int], source: str
    ) -> AromaRecipe | None:
        raw_stages = data.get("stages")
        if not isinstance(raw_stages, list):
            return None
        stages: list[dict] = []
        remaining = self._max_total_seconds()
        for raw_stage in raw_stages:
            if not isinstance(raw_stage, dict) or remaining <= 0:
                continue
            raw_names = raw_stage.get("channels", [])
            if not isinstance(raw_names, list):
                continue
            names = [str(name).lower() for name in raw_names if str(name).lower() in channel_map]
            names = list(dict.fromkeys(names))[:3]
            if not names:
                continue
            try:
                duration = int(raw_stage.get("duration_seconds", 0))
            except (TypeError, ValueError):
                continue
            duration = min(max(duration, 1), self._max_stage_seconds(), remaining)
            remaining -= duration
            stages.append(
                {
                    "channel_names": names,
                    "channel_numbers": [channel_map[name] for name in names],
                    "duration_seconds": duration,
                }
            )
        if not stages:
            return None
        summary = str(data.get("summary", "个性化香薰方案")).strip()[:80]
        return AromaRecipe(summary=summary or "个性化香薰方案", stages=stages, source=source)

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
                result[str(name).lower()] = channel_number
        return result

    def _max_stage_seconds(self) -> int:
        return max(1, min(int(self._config.get_config("AROMA.MAX_STAGE_SECONDS", 600)), 3600))

    def _max_total_seconds(self) -> int:
        return max(1, min(int(self._config.get_config("AROMA.MAX_TOTAL_SECONDS", 1800)), 14400))
