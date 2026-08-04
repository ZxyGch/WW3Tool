"""仓库根目录解析（desktop 专用）。

``WW3TOOL_ROOT`` 环境变量优先（pip/brew 安装形态下指向含
meshgen/public/params.yml 的仓库），否则按仓库布局从本文件推导：
``<仓库根>/src/desktop/``，向上 2 级即仓库根。

[EN] Repo-root resolution for the desktop package: WW3TOOL_ROOT env wins
(packaged installs); otherwise inferred from the repo layout.
"""

import os
from pathlib import Path


def repo_root() -> Path:
    env_root = os.environ.get("WW3TOOL_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()
    return Path(__file__).resolve().parents[2]
