# -*- coding: utf-8 -*-
import re
from typing import Optional, Tuple

from .base import KeywordConverter
from .bpe_converter import BpeConverter
from .pinyin_converter import PinyinConverter

__all__ = [
    "KeywordConverter",
    "PinyinConverter",
    "BpeConverter",
    "detect_language",
    "get_converter",
    "convert_wake_word",
    "wake_word_text_to_keyword_line",
]

# Singleton converters
_pinyin_converter: Optional[PinyinConverter] = None
_bpe_converter: Optional[BpeConverter] = None


def _get_pinyin_converter() -> PinyinConverter:
    """Get or create PinyinConverter singleton."""
    global _pinyin_converter
    if _pinyin_converter is None:
        _pinyin_converter = PinyinConverter()
    return _pinyin_converter


def _get_bpe_converter() -> BpeConverter:
    """Get or create BpeConverter singleton."""
    global _bpe_converter
    if _bpe_converter is None:
        _bpe_converter = BpeConverter()
    return _bpe_converter


def detect_language(text: str) -> str:
    # Check for Chinese characters
    chinese_pattern = re.compile(r"[\u4e00-\u9fff]")
    if chinese_pattern.search(text):
        return "zh"
    return "en"


def get_converter(language: str) -> KeywordConverter:
    if language == "zh":
        return _get_pinyin_converter()
    elif language == "en":
        return _get_bpe_converter()
    else:
        raise ValueError(f"Unsupported language: {language}")


def wake_word_text_to_keyword_line(text: str, tokens_path: str) -> str:
    """Convert Chinese text to the current keywords.txt line format.

    Output format: "token token token @原始唤醒词".
    """
    converter = _get_pinyin_converter()
    return converter.convert(text, tokens_path=tokens_path)


def convert_wake_word(text: str) -> Tuple[str, str, str]:
    language = detect_language(text)
    converter = get_converter(language)
    if language == "zh":
        from src.utils.resource_finder import get_app_root

        tokens_path = get_app_root() / converter.model_path / "tokens.txt"
        keyword_line = converter.convert(text, tokens_path=tokens_path)
    else:
        keyword_line = converter.convert(text)
    return keyword_line, language, converter.model_path
