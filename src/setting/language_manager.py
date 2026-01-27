"""
语言管理模块
用于加载和切换应用程序的语言
"""
import os
import json
from setting.config import PUBLIC_DIR, load_config

# 语言文件目录
LANGUAGE_DIR = os.path.join(PUBLIC_DIR, "languages")
os.makedirs(LANGUAGE_DIR, exist_ok=True)

# 支持的语言列表
SUPPORTED_LANGUAGES = {
    "zh_CN": "简体中文",
    "en_US": "English"
}

# 默认语言
DEFAULT_LANGUAGE = "zh_CN"

# 全局语言字典
_translations = {}
_current_language = DEFAULT_LANGUAGE


def get_language_file_path(language_code):
    """获取语言文件路径"""
    return os.path.join(LANGUAGE_DIR, f"{language_code}.json")


def load_language(language_code):
    """加载指定语言的文件"""
    global _translations, _current_language
    
    language_file = get_language_file_path(language_code)
    
    if not os.path.exists(language_file):
        # 如果语言文件不存在，返回默认语言
        if language_code != DEFAULT_LANGUAGE:
            return load_language(DEFAULT_LANGUAGE)
        # 如果默认语言文件也不存在，返回空字典
        _translations = {}
        _current_language = DEFAULT_LANGUAGE
        return {}
    
    try:
        with open(language_file, 'r', encoding='utf-8') as f:
            _translations = json.load(f)
            _current_language = language_code
            return _translations
    except Exception as e:
        print(f"加载语言文件失败: {e}")
        _translations = {}
        _current_language = DEFAULT_LANGUAGE
        return {}


def get_current_language():
    """获取当前语言代码"""
    return _current_language


def set_language(language_code):
    """设置当前语言"""
    if language_code in SUPPORTED_LANGUAGES:
        load_language(language_code)
        return True
    return False


def translate(key, default=None):
    """翻译键值，如果找不到则返回默认值或键本身"""
    if default is None:
        default = key
    
    # 直接访问扁平化的字典
    try:
        value = _translations[key]
        return value if isinstance(value, str) else default
    except (KeyError, TypeError):
        return default


def tr(key, default=None):
    """翻译函数的简写"""
    return translate(key, default)


def get_supported_languages():
    """获取支持的语言列表"""
    return SUPPORTED_LANGUAGES.copy()


def load_language_from_config():
    """从配置文件加载语言设置并应用"""
    config = load_config()
    language_code = config.get("LANGUAGE", "zh_CN")
    return load_language(language_code)


load_language_from_config()
