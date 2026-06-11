"""迁移自旧版代码的翻译函数。

本模块属于 ``support/`` 支撑层。src2 Desktop 目前直接在界面展示中文，
但自旧版迁移的服务仍保留 ``tr(key, default)`` 消息键调用形式；
本函数读取 ``public/languages/<LANGUAGE>.json``，语言代码来自
``public/config.json`` 的 ``LANGUAGE`` 字段。

主要消费者：
- ``infrastructure/`` 中自 src 迁移的 NetCDF、网格、WW3 相关服务
"""

from __future__ import annotations

import json
from pathlib import Path

_translations: dict[str, str] = {}
_current_language: str | None = None


def set_language(language_code: str) -> None:
    """切换当前语言并清空缓存，供设置页即时应用。"""
    global _current_language, _translations
    _current_language = str(language_code or "zh_CN")
    _translations = _load_language(_current_language)


def tr(_key: str, default: str | None = None) -> str:
    """按当前配置语言翻译消息键，缺失时返回默认文案或消息键。

    Args:
        _key: 消息键。
        default: 优先返回的默认字符串；为 ``None`` 时退回 ``_key``。

    Returns:
        用于展示的本地化或回退文本。
    """
    global _current_language, _translations
    language = _current_language or _configured_language()
    if not _translations:
        _current_language = language
        _translations = _load_language(language)
    return _translations.get(_key) or default or _key


def _configured_language() -> str:
    try:
        from workflows.infrastructure import runtime_config

        return str(runtime_config.load_config().get("LANGUAGE", "zh_CN") or "zh_CN")
    except Exception:
        return "zh_CN"


def _load_language(language: str) -> dict[str, str]:
    root = Path(__file__).resolve().parents[3]
    path = root / "public" / "languages" / f"{language}.json"
    if not path.is_file() and language != "zh_CN":
        path = root / "public" / "languages" / "zh_CN.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return {str(key): str(value) for key, value in data.items()}
