"""迁移自旧版代码的翻译函数。

本模块属于 ``support/`` 支撑层。src Desktop 目前直接在界面展示中文，
但自旧版迁移的服务仍保留 ``tr(key, default)`` 消息键调用形式；
本函数读取 ``public/languages/<语言码>.json``；语言码取自 params.yml 的
``desktop.language``，该项留空或写 ``auto`` 时按 ``LC_ALL``/``LANG`` 等环境变量推断。

主要消费者：
- ``infrastructure/`` 中自 src 迁移的 NetCDF、网格、WW3 相关服务

[EN] Translation function migrated from legacy code.

This module belongs to the ``support/`` layer. The src Desktop currently displays
Chinese directly in the UI, but services migrated from the legacy codebase still
use the ``tr(key, default)`` message-key calling convention. This function reads
``public/languages/<code>.json``; the code comes from ``desktop.language`` in
params.yml, and is inferred from ``LC_ALL``/``LANG`` when that is blank or ``auto``.

Main consumers:
- ``infrastructure/`` NetCDF, grid, and WW3 related services migrated from src
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

# 内置语言包；语言码认不出来时一律退回英文，而不是退回中文。
# [EN] Bundled languages; an unrecognized code falls back to English, never Chinese.
SUPPORTED_LANGUAGES = ("zh_CN", "en_US")
DEFAULT_LANGUAGE = "en_US"
AUTO_LANGUAGE = "auto"

# 表示"跟随环境"的写法：留空、auto，以及 C/POSIX 这类"不做本地化"的 locale。
# [EN] Spellings meaning "follow the environment": empty, auto, and non-localized locales like C/POSIX.
_AUTO_TOKENS = frozenset({"", "auto", "system", "default", "none", "null"})
_NEUTRAL_LOCALES = frozenset({"c", "posix"})

_translations: dict[str, str] = {}
_current_language: str | None = None


def normalize_language(value: object) -> str | None:
    """把任意 locale 写法归一到内置语言码，认不出或表示"跟随环境"时返回 ``None``。

    接受 ``zh_CN``、``zh-Hans``、``en_US.UTF-8`` 这类写法；``C``/``POSIX`` 视为
    未本地化，与留空同样交给调用方去问环境。

    [EN] Normalize any locale spelling to a bundled language code; return ``None``
    when unrecognized or when it means "follow the environment".
    """
    text = str(value or "").strip()
    if text.lower() in _AUTO_TOKENS:
        return None
    # 剥掉 .UTF-8 / @euro 之类的后缀，只留语言与地区
    # [EN] Strip suffixes like .UTF-8 / @euro, keeping only language and region.
    tag = re.split(r"[.@]", text.replace("-", "_"), maxsplit=1)[0].lower()
    if tag in _NEUTRAL_LOCALES:
        return None
    if tag.startswith("zh"):
        return "zh_CN"
    if tag.startswith("en"):
        return "en_US"
    return None


def _windows_ui_language() -> str | None:
    """Windows 上没有 LANG 变量，改问系统界面语言。

    [EN] Windows has no LANG variable, so ask the system UI language instead.
    """
    if os.name != "nt":
        return None
    try:
        import ctypes

        langid = ctypes.windll.kernel32.GetUserDefaultUILanguage()  # type: ignore[attr-defined]
    except Exception:
        return None
    # LANGID 低 10 位是主语言号，0x04 即中文
    # [EN] The low 10 bits of a LANGID are the primary language; 0x04 is Chinese.
    return "zh_CN" if (int(langid) & 0x3FF) == 0x04 else DEFAULT_LANGUAGE


def language_from_environment() -> str:
    """按 POSIX 优先级读环境变量推断语言，问不出来时用英文。

    先设先赢：``LC_ALL`` 一旦设成 ``C``，就说明用户要的是未本地化的输出，
    不再往下看 ``LANG``。

    [EN] Infer the language from environment variables in POSIX precedence order,
    falling back to English. First one set wins: an ``LC_ALL`` of ``C`` means the
    user asked for non-localized output, so ``LANG`` is not consulted afterwards.
    """
    for name in ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"):
        raw = os.environ.get(name)
        if raw and raw.strip():
            # LANGUAGE 是冒号分隔的优先级列表，取第一项
            # [EN] LANGUAGE is a colon-separated priority list; take the first entry.
            return normalize_language(raw.split(":")[0]) or DEFAULT_LANGUAGE
    return _windows_ui_language() or DEFAULT_LANGUAGE


def resolve_language() -> str:
    """当前该用的语言：配置里显式指定的优先，否则跟随环境。

    配置读不出来（首次运行、家目录只读、YAML 损坏）时同样交给环境判断，
    而不是硬退回某一种语言。

    [EN] The language to use: an explicit setting wins, otherwise follow the
    environment. A config that cannot be read (first run, read-only home, broken
    YAML) also defers to the environment instead of hard-coding one language.
    """
    configured: object = None
    try:
        from workflows.infrastructure import runtime_config

        configured = runtime_config.load_config().get("LANGUAGE")
    except Exception:
        configured = None
    return normalize_language(configured) or language_from_environment()


def set_language(language_code: str) -> None:
    """切换当前语言并清空缓存，供设置页即时应用。

    传入 ``auto`` 或空值表示改回跟随环境。

    [EN] Switch the current language and clear the cache for immediate application
    by the settings page. Passing ``auto`` or an empty value returns to following
    the environment.
    """
    global _current_language, _translations
    _current_language = normalize_language(language_code) or language_from_environment()
    _translations = _load_language(_current_language)


def tr(_key: str, default: str | None = None) -> str:
    """按当前配置语言翻译消息键，缺失时返回默认文案或消息键。

    Args:
        _key: 消息键。
        default: 优先返回的默认字符串；为 ``None`` 时退回 ``_key``。

    Returns:
        用于展示的本地化或回退文本。

    [EN] Translate a message key according to the current configured language;
    fall back to the default text or the message key if missing.

    Args:
        _key: Message key.
        default: Preferred fallback string; returns ``_key`` when ``None``.

    Returns:
        Localized or fallback text for display.
    """
    global _current_language, _translations
    language = _current_language or resolve_language()
    if not _translations:
        _current_language = language
        _translations = _load_language(language)
    return _translations.get(_key) or default or _key


def _load_language(language: str) -> dict[str, str]:
    env_root = os.environ.get("WW3TOOL_ROOT")
    if env_root:
        root = Path(env_root).expanduser().resolve()
    else:
        root = None
        # 仓库形态：从本文件向上找到含 params.yml 与 run.py 的仓库根
        # [EN] Repo layout: walk up to the dir holding both params.yml and run.py.
        _d = Path(__file__).resolve().parent
        while True:
            if (_d / "params.yml").is_file() and (_d / "run.py").is_file():
                root = _d
                break
            if _d.parent == _d:
                break
            _d = _d.parent
        if root is None:
            # 装包形态：site-packages 里的 ww3tool_resources 自带语言文件
            # [EN] Packaged install: ww3tool_resources ships the language files.
            try:
                import ww3tool_resources

                pkg_root = Path(ww3tool_resources.__file__).resolve().parent
                if (pkg_root / "params.yml").is_file():
                    root = pkg_root
            except Exception:
                pass
        if root is None:
            root = Path(__file__).resolve().parents[3]
    path = root / "public" / "languages" / f"{language}.json"
    if not path.is_file() and language != DEFAULT_LANGUAGE:
        path = root / "public" / "languages" / f"{DEFAULT_LANGUAGE}.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return {str(key): str(value).replace("\\n", "\n") for key, value in data.items()}
