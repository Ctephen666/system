# -*- coding: utf-8 -*-
import re
from pathlib import Path
from typing import List

from .base import KeywordConverter

# 声母列表（按长度降序排列以优先匹配长声母）
INITIALS = [
    "zh", "ch", "sh",  # 翘舌音（2字符，优先匹配）
    "b", "p", "m", "f",  # 唇音
    "d", "t", "n", "l",  # 舌尖音
    "g", "k", "h",  # 舌根音
    "j", "q", "x",  # 舌面音
    "r", "z", "c", "s",  # 其他
    "y", "w",  # 零声母标记
]


class PinyinConverter(KeywordConverter):
    def __init__(self):
        self._pypinyin = None
        self._style = None

    def _ensure_pypinyin(self):
        if self._pypinyin is None:
            try:
                from pypinyin import Style, lazy_pinyin
                self._pypinyin = lazy_pinyin
                self._style = Style.TONE
            except ImportError:
                raise ImportError(
                    "pypinyin is required for Chinese wake word conversion. "
                    "Install it with: pip install pypinyin"
                )

    @property
    def language(self) -> str:
        return "zh"

    @property
    def model_path(self) -> str:
        return "models/zh"

    def can_convert(self, text: str) -> bool:
        chinese_pattern = re.compile(r"[\u4e00-\u9fff]")
        return bool(chinese_pattern.search(text))

    def _split_pinyin(self, pinyin: str) -> List[str]:
        if not pinyin:
            return []

        pinyin_lower = pinyin.lower()

        for initial in INITIALS:
            if pinyin_lower.startswith(initial):
                final = pinyin[len(initial):]
                if final:
                    return [initial, final]
                else:
                    return [initial]

        return [pinyin]

    def _load_tokens(self, tokens_path: str | Path) -> set[str]:
        tokens = set()
        with open(tokens_path, encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split()
                if parts:
                    tokens.add(parts[0])
        return tokens

    def convert(self, text: str, tokens_path: str | Path | None = None) -> str:
        self._ensure_pypinyin()

        pinyin_list = self._pypinyin(text, style=self._style)

        split_parts = []
        for pinyin in pinyin_list:
            parts = self._split_pinyin(pinyin)
            split_parts.extend(parts)

        if tokens_path is not None:
            valid_tokens = self._load_tokens(tokens_path)
            for pinyin in pinyin_list:
                parts = self._split_pinyin(pinyin)
                missing = [part for part in parts if part not in valid_tokens]
                if missing:
                    raise ValueError(
                        f"“{text}” 中的拼音 “{pinyin}” 无法映射到 tokens.txt: "
                        + ", ".join(missing)
                    )

        pinyin_str = " ".join(split_parts)
        return f"{pinyin_str} @{text}"
