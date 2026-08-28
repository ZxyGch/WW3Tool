"""本地文件系统路径的规范化工具。

桌面端和 workflows 层共用：把用户给出的路径统一成当前平台的写法，
避免同一个目录在配置里出现两种拼写而互相比不相等。

[EN] Local filesystem path helpers shared by the desktop UI and the workflows.
"""

from __future__ import annotations

import os

_QUOTES = ('"', "'")


def normalize_local_path(value) -> str:
    """把 *value* 写成当前平台的路径形式。

    针对的是 Windows 上真实会遇到的几种输入：

    - Qt 的文件对话框在所有平台都返回正斜杠（``C:/Users/...``），而应用内部
      用 :func:`os.path.join` 拼出来的是反斜杠，两者字符串永远不相等；
    - 资源管理器的"复制为路径"会把路径连同两侧双引号一起放进剪贴板；
    - 手输时可能带 ``~`` 或 ``%USERPROFILE%`` / ``$HOME``。

    相对路径保持相对（有几项设置本来就允许相对于项目根目录），空值返回空串。

    [EN] Rewrite *value* the way the current platform writes paths: strip the
    quotes Explorer's "Copy as path" adds, expand ``~`` and environment
    variables, and switch the separators.  Relative stays relative.
    """
    text = str(value or "").strip()
    if not text:
        return ""

    if len(text) >= 2 and text[0] == text[-1] and text[0] in _QUOTES:
        text = text[1:-1].strip()
        if not text:
            return ""

    text = os.path.expandvars(os.path.expanduser(text))
    normalized = os.path.normpath(text)

    # normpath("C:") leaves a drive-relative path, which is virtually never
    # what the user meant by typing a bare drive.
    if (
        os.name == "nt"
        and len(normalized) == 2
        and normalized[1] == ":"
        and normalized[0].isalpha()
    ):
        normalized += os.sep

    return normalized


def local_path_key(value) -> str:
    """比较用的键：同一个位置的不同拼写映射到同一个键。

    Windows 上大小写不敏感，因此还要过一遍 :func:`os.path.normcase`。

    [EN] Comparison key for two local paths that may be spelled differently.
    """
    normalized = normalize_local_path(value)
    if not normalized:
        return ""
    return os.path.normcase(os.path.abspath(normalized))


def same_local_path(first, second) -> bool:
    """两个路径是否指向同一个位置（不要求路径已存在）。

    [EN] True when both spellings name the same local path.
    """
    return local_path_key(first) == local_path_key(second)
