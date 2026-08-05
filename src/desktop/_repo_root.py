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
    # 仓库形态：从本文件向上找到含 params.yml 与 run.py 的仓库根
    # [EN] Repo layout: walk up to the dir holding both params.yml and run.py.
    _d = Path(__file__).resolve().parent
    while True:
        if (_d / "params.yml").is_file() and (_d / "run.py").is_file():
            return _d
        if _d.parent == _d:
            break
        _d = _d.parent
    # 装包形态：site-packages 里的 ww3tool_resources 自带全部运行资源
    # [EN] Packaged install: ww3tool_resources ships the runtime resources.
    try:
        import ww3tool_resources

        pkg_root = Path(ww3tool_resources.__file__).resolve().parent
        if (pkg_root / "params.yml").is_file():
            return pkg_root
    except Exception:
        pass
    return Path(__file__).resolve().parents[2]  # 兜底：原仓库推断
