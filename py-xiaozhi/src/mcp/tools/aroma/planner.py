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
        if not channel_map:
            raise RuntimeError("香薰通道映射为空，无法生成配方")
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
        raw_api_key = self._config.get_config("AROMA.QWEN.API_KEY", "")
        api_key = raw_api_key.strip() if isinstance(raw_api_key, str) else ""
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
                base_url=str(self._config.get_config("AROMA.QWEN.BASE_URL", "")).strip()
                or None,
                http_client=httpx.Client(timeout=timeout),
                max_retries=0,
            )
            try:
                response = client.chat.completions.create(
                    model=self._config.get_config("AROMA.QWEN.MODEL", "qwen3.6-plus"),
                    messages=[
                        {
                            "role": "system",
                            "content": self._system_prompt(channel_map),
                        },
                        {"role": "user", "content": requirement},
                    ],
                    temperature=0.2,
                    max_tokens=600,
                )
                content = response.choices[0].message.content or ""
            finally:
                client.close()
            return self._parse_json(content)
        except Exception as error:
            logger.warning(
                "[AromaPlanner] Qwen 配方生成失败，改用本地规则: %s",
                self._redact_error(str(error), api_key),
            )
            return None

    @staticmethod
    def _redact_error(message: str, api_key: str) -> str:
        """防止异常文本意外将配置中的 API 密钥写入日志。"""
        return message.replace(api_key, "***") if api_key else message

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
        pattern = [0] * 16
        for name in available_names[:3]:
            pattern[channel_map[name] - 1] = self._default_on_value()
        stage = {
            "pattern": pattern,
            "channel_names": available_names[:3],
            "channel_numbers": [channel_map[name] for name in available_names[:3]],
            "duration_seconds": self._target_total_seconds(),
        }
        return AromaRecipe(summary=summary, stages=[stage], source="local_rule")

    def _validate_recipe(
        self, data: dict[str, Any], channel_map: dict[str, int], source: str
    ) -> AromaRecipe | None:
        raw_stages = data.get("stages")
        if not isinstance(raw_stages, list):
            return None
        stages: list[dict] = []
        remaining = self._target_total_seconds()
        for raw_stage in raw_stages:
            if not isinstance(raw_stage, dict) or remaining <= 0:
                continue
            pattern = self._validate_pattern(raw_stage.get("pattern"))
            if pattern is None:
                continue
            try:
                duration = int(raw_stage.get("duration_seconds", 0))
            except (TypeError, ValueError):
                continue
            duration = min(max(duration, 1), self._max_stage_seconds(), remaining)
            remaining -= duration
            stages.append(
                {
                    "pattern": pattern,
                    "channel_names": [
                        name for name, number in channel_map.items()
                        if pattern[number - 1] != 0
                    ],
                    "channel_numbers": [
                        number for number, value in enumerate(pattern, 1)
                        if value != 0
                    ],
                    "duration_seconds": duration,
                }
            )
        if not stages:
            return None
        total = sum(stage["duration_seconds"] for stage in stages)
        if total < self._target_total_seconds():
            stages[-1]["duration_seconds"] += self._target_total_seconds() - total
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
        configured = int(self._config.get_config("AROMA.MAX_STAGE_SECONDS", 600))
        return max(1, min(configured, 3600))

    def _max_total_seconds(self) -> int:
        configured = int(self._config.get_config("AROMA.MAX_TOTAL_SECONDS", 1800))
        return max(1, min(configured, 14400))

    def _target_total_seconds(self) -> int:
        configured = int(
            self._config.get_config(
                "AROMA.TOTAL_DURATION_SECONDS",
                self._config.get_config("AROMA.MAX_TOTAL_SECONDS", 30),
            )
        )
        return max(1, min(configured, self._max_total_seconds()))

    def _pattern_mode(self) -> str:
        mode = str(self._config.get_config("AROMA.PATTERN_MODE", "binary")).lower()
        return mode if mode in {"binary", "concentration"} else "binary"

    def _default_on_value(self) -> int:
        return 1 if self._pattern_mode() == "binary" else int(
            self._config.get_config("AROMA.DEFAULT_CONCENTRATION", 100)
        )

    def _pattern_value_description(self) -> str:
        return "0或1" if self._pattern_mode() == "binary" else "0到100的整数"

    def _system_prompt(self, channel_map: dict[str, int]) -> str:
        benefits = {
            "lavender": "放松、助眠",
            "bergamot": "舒缓情绪",
            "rosemary": "专注、清醒",
            "lemon": "清新、提神",
            "peppermint": "强提神",
            "chamomile": "安抚、助眠",
            "cedarwood": "沉静、稳定",
            "eucalyptus": "清爽",
            "jasmine": "舒缓、愉悦",
            "rose": "放松、愉悦",
            "sandalwood": "安定、冥想",
            "ylang_ylang": "舒缓压力",
            "tea_tree": "清新",
            "orange": "愉悦、提振",
            "frankincense": "沉静、冥想",
            "vanilla": "温暖、放松",
        }
        mapping_lines = []
        for name, number in sorted(channel_map.items(), key=lambda item: item[1]):
            mapping_lines.append(
                f"通道{number} / pattern第{number}位：{name}（{benefits.get(name, '按配置香型使用')}）"
            )
        mapping = "\n".join(mapping_lines)
        return (
            "你是香薰配方规划器，只能返回一个 JSON 对象，不得输出 Markdown、解释或额外文字。\n"
            'JSON 格式：{"summary":"简短中文摘要","stages":[{"pattern":[16个数字],"duration_seconds":整数}]}\n'
            "通道和香型映射如下（pattern 第 N 位严格对应继电器 N，不能调整顺序）：\n"
            f"{mapping}\n"
            f"pattern 必须恰好 16 个值；当前允许值为{self._pattern_value_description()}。\n"
            "只输出 pattern，不得输出 channels、channel_numbers 或其他控制字段。\n"
            "根据用户的情绪、场景和目标选择 1～4 个合适香型；不确定时选择较温和的组合。\n"
            f"所有阶段总时长必须严格为 {self._target_total_seconds()} 秒；最多输出 4 个阶段。\n"
            "不要同时堆叠所有香型，不要输出不存在于映射中的香型，不要编造硬件通道。\n"
            "用户需求将作为下一条消息提供。"
        )

    def _validate_pattern(self, raw_pattern: Any) -> list[int] | None:
        if not isinstance(raw_pattern, list) or len(raw_pattern) != 16:
            return None
        try:
            pattern = [int(value) for value in raw_pattern]
        except (TypeError, ValueError):
            return None
        if self._pattern_mode() == "binary":
            return pattern if all(value in (0, 1) for value in pattern) else None
        return pattern if all(0 <= value <= 100 for value in pattern) else None
