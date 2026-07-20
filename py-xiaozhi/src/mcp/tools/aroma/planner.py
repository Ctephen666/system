"""香薰配方校验、君臣佐使配伍和本地兜底库。"""

import json
from dataclasses import dataclass
from typing import Any

from src.utils.config_manager import ConfigManager


ROLE_ORDER = ("jun", "chen", "zuo", "shi")
ROLE_LABELS = {"jun": "君香", "chen": "臣香", "zuo": "佐香", "shi": "使香"}

# canonical name: (配伍角色, 中文名, 香气体验说明)
AROMA_ROLE_CATALOG: dict[str, tuple[str, str, str]] = {
    "lavender": ("jun", "薰衣草", "柔和舒缓"),
    "rosemary": ("jun", "迷迭香", "清醒专注"),
    "peppermint": ("jun", "薄荷", "清凉醒脑"),
    "orange": ("jun", "甜橙", "明亮愉悦"),
    "bergamot": ("chen", "佛手柑", "清新协同"),
    "lemon": ("chen", "柠檬", "清新提振"),
    "chamomile": ("chen", "洋甘菊", "温和陪衬"),
    "eucalyptus": ("chen", "尤加利", "通透清爽"),
    "jasmine": ("zuo", "茉莉", "柔和调香"),
    "rose": ("zuo", "玫瑰", "圆润平衡"),
    "ylang_ylang": ("zuo", "依兰", "甜润调和"),
    "tea_tree": ("zuo", "茶树", "清新平衡"),
    "cedarwood": ("shi", "雪松", "木质收束"),
    "sandalwood": ("shi", "檀香", "温润定调"),
    "frankincense": ("shi", "乳香", "沉静延展"),
    "vanilla": ("shi", "香草", "温暖收尾"),
}

AROMA_NAME_ALIASES = {
    "薰衣草": "lavender", "佛手柑": "bergamot", "迷迭香": "rosemary",
    "柠檬": "lemon", "薄荷": "peppermint", "洋甘菊": "chamomile",
    "罗马洋甘菊": "chamomile", "雪松": "cedarwood", "尤加利": "eucalyptus",
    "茉莉": "jasmine", "玫瑰": "rose", "檀香": "sandalwood",
    "依兰": "ylang_ylang", "依兰依兰": "ylang_ylang", "茶树": "tea_tree",
    "甜橙": "orange", "橙子": "orange", "乳香": "frankincense", "香草": "vanilla",
}

# Each scenario has exactly one preferred aroma from each role.
FIXED_SCENARIOS: tuple[tuple[tuple[str, ...], dict[str, str], str], ...] = (
    (("睡前", "睡觉", "失眠", "助眠", "晚安"), {"jun":"lavender","chen":"chamomile","zuo":"rose","shi":"sandalwood"}, "夜间舒缓"),
    (("放松", "压力", "紧张", "解压"), {"jun":"lavender","chen":"bergamot","zuo":"ylang_ylang","shi":"vanilla"}, "放松舒缓"),
    (("专注", "学习", "工作", "阅读", "写作"), {"jun":"rosemary","chen":"lemon","zuo":"tea_tree","shi":"frankincense"}, "清醒专注"),
    (("早上", "晨起", "起床", "提神", "困", "精神"), {"jun":"peppermint","chen":"eucalyptus","zuo":"jasmine","shi":"cedarwood"}, "晨间清新"),
    (("开心", "愉快", "心情", "阳光"), {"jun":"orange","chen":"bergamot","zuo":"jasmine","shi":"vanilla"}, "明亮心情"),
    (("冥想", "静心", "瑜伽", "放空"), {"jun":"lavender","chen":"chamomile","zuo":"tea_tree","shi":"frankincense"}, "静心沉稳"),
    (("清新", "净味", "空气", "打扫"), {"jun":"peppermint","chen":"eucalyptus","zuo":"tea_tree","shi":"cedarwood"}, "清新净味"),
    (("浪漫", "约会", "花香", "氛围"), {"jun":"orange","chen":"bergamot","zuo":"rose","shi":"vanilla"}, "花香暖意"),
    (("下雨", "雨天", "阴天", "宅家"), {"jun":"lavender","chen":"chamomile","zuo":"ylang_ylang","shi":"cedarwood"}, "雨日沉静"),
    (("夏天", "炎热", "凉快", "清凉"), {"jun":"peppermint","chen":"lemon","zuo":"tea_tree","shi":"cedarwood"}, "夏日清凉"),
    (("冬天", "寒冷", "温暖", "暖和"), {"jun":"orange","chen":"bergamot","zuo":"rose","shi":"frankincense"}, "冬日暖香"),
)
DEFAULT_SCENARIO = {"jun":"lavender","chen":"bergamot","zuo":"jasmine","shi":"vanilla"}
# Backwards-compatible catalogue view for callers that only need scenario coverage.
FIXED_AROMA_RECIPES = tuple(
    (keywords, tuple(roles.values()), summary)
    for keywords, roles, summary in FIXED_SCENARIOS
)


@dataclass(frozen=True)
class AromaRecipe:
    """可安全执行的四路香薰配方。"""

    summary: str
    stages: list[dict[str, Any]]
    source: str
    role_details: list[dict[str, Any]]
    overall_effect: str
    voice_message: str


class AromaPlanner:
    """校验服务端四角色方案，并在不可用时选择本地四角色配方。"""

    def __init__(self, config: ConfigManager):
        self._config = config

    async def create_recipe(self, requirement: str, server_recipe: str | dict[str, Any] | None = None) -> AromaRecipe:
        channel_map = self._channel_map()
        if not channel_map:
            raise RuntimeError("香薰通道映射为空，无法生成配方")
        data = self._parse_recipe(server_recipe)
        if data is not None:
            recipe = self._validate_server_recipe(data, channel_map)
            if recipe is not None:
                return recipe
        return self._fixed_library_recipe(requirement, channel_map)

    @staticmethod
    def _parse_recipe(raw_recipe: str | dict[str, Any] | None) -> dict[str, Any] | None:
        if isinstance(raw_recipe, dict):
            return raw_recipe
        if not isinstance(raw_recipe, str) or not raw_recipe.strip():
            return None
        try:
            data = json.loads(raw_recipe)
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, dict) else None

    def _validate_server_recipe(self, data: dict[str, Any], channel_map: dict[str, int]) -> AromaRecipe | None:
        if data.get("duration_seconds") != self._target_total_seconds():
            return None
        roles = data.get("roles")
        if not isinstance(roles, dict) or set(roles) != set(ROLE_ORDER):
            return None
        resolved = self._resolve_roles(roles, channel_map, allow_substitution=False)
        if resolved is None:
            return None
        summary = data.get("summary", "个性化香薰方案")
        effect = data.get("overall_effect")
        return self._build_recipe(
            str(summary)[:80] or "个性化香薰方案",
            resolved,
            "xiaozhi_server",
            effect if isinstance(effect, str) else None,
        )

    def _fixed_library_recipe(self, requirement: str, channel_map: dict[str, int]) -> AromaRecipe:
        chosen = DEFAULT_SCENARIO
        summary = "日常舒缓"
        for keywords, roles, candidate_summary in FIXED_SCENARIOS:
            if any(keyword in requirement.lower() for keyword in keywords):
                chosen, summary = roles, candidate_summary
                break
        resolved = self._resolve_roles(chosen, channel_map, allow_substitution=True)
        if resolved is None:
            raise RuntimeError("君臣佐使四类香薰通道未完整配置，无法输出四路配方")
        return self._build_recipe(summary, resolved, "fixed_library")

    def _resolve_roles(self, roles: dict[str, Any], channel_map: dict[str, int], *, allow_substitution: bool) -> dict[str, str] | None:
        resolved: dict[str, str] = {}
        used_names: set[str] = set()
        used_channels: set[int] = set()
        for role in ROLE_ORDER:
            value = roles.get(role)
            raw_name = value.get("aroma") if isinstance(value, dict) else value
            name = AROMA_NAME_ALIASES.get(str(raw_name).strip().lower(), str(raw_name).strip().lower())
            candidates = [name]
            if allow_substitution:
                candidates.extend(candidate for candidate, info in AROMA_ROLE_CATALOG.items() if info[0] == role and candidate != name)
            selected = next((candidate for candidate in candidates if candidate in channel_map and candidate not in used_names and channel_map[candidate] not in used_channels and AROMA_ROLE_CATALOG.get(candidate, (None,))[0] == role), None)
            if selected is None:
                return None
            resolved[role] = selected
            used_names.add(selected)
            used_channels.add(channel_map[selected])
        return resolved

    def _build_recipe(
        self,
        summary: str,
        roles: dict[str, str],
        source: str,
        overall_effect: str | None = None,
    ) -> AromaRecipe:
        channel_map = self._channel_map()
        names = [roles[role] for role in ROLE_ORDER]
        details = [{"role": ROLE_LABELS[role], "role_key": role, "aroma": AROMA_ROLE_CATALOG[name][1], "canonical_name": name, "channel": channel_map[name], "effect": AROMA_ROLE_CATALOG[name][2]} for role, name in ((role, roles[role]) for role in ROLE_ORDER)]
        pattern = [0] * 16
        for detail in details:
            pattern[detail["channel"] - 1] = self._default_on_value()
        effect = (overall_effect or self._default_overall_effect(roles)).strip()[:40]
        voice_message = f"本次整体香气体验为{effect}。" + "配伍为：" + "；".join(f"{detail['role']}为{detail['aroma']}，{detail['effect']}" for detail in details) + "。"
        return AromaRecipe(summary, [{"pattern": pattern, "channel_names": names, "channel_numbers": [detail["channel"] for detail in details], "duration_seconds": self._target_total_seconds()}], source, details, effect, voice_message)

    @staticmethod
    def _default_overall_effect(roles: dict[str, str]) -> str:
        return {
            "lavender": "柔和放松",
            "rosemary": "清醒专注",
            "peppermint": "清凉提神",
            "orange": "明亮愉悦",
        }.get(roles["jun"], "平衡舒缓")

    def _channel_map(self) -> dict[str, int]:
        raw_map = self._config.get_config("AROMA.CHANNEL_MAP", {})
        if not isinstance(raw_map, dict):
            return {}
        return {str(name).strip().lower(): int(channel) for name, channel in raw_map.items() if str(channel).isdigit() and 1 <= int(channel) <= 16}

    def _target_total_seconds(self) -> int:
        return max(1, min(int(self._config.get_config("AROMA.TOTAL_DURATION_SECONDS", 30)), int(self._config.get_config("AROMA.MAX_TOTAL_SECONDS", 1800))))

    def _default_on_value(self) -> int:
        return 1 if str(self._config.get_config("AROMA.PATTERN_MODE", "binary")).lower() == "binary" else int(self._config.get_config("AROMA.DEFAULT_CONCENTRATION", 100))
