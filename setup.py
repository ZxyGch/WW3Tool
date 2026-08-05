"""WW3Tool 打包配置 + 构建期资源暂存。

布局：``run.py`` 在仓库根（作为 py-module 打进 wheel 顶层），源码包
``workflows/``、``desktop/`` 位于 ``src/`` 下；运行所需资源
（``params.yml``、``public/`` 子集、``meshgen/`` 瘦身子集、
``src/requirements.txt``）在构建时暂存进 ``src/ww3tool_resources/`` 包，
使 ``pip install ww3tool`` 自包含、安装后无需 ``WW3TOOL_ROOT`` 即可定位
模板 / 翻译 / 网格生成器。

[EN] Packaging config + build-time resource staging. The wheel ships a
self-contained ww3tool_resources package with all runtime resources.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from setuptools import setup

_ROOT = Path(__file__).resolve().parent
_STAGE = _ROOT / "src" / "ww3tool_resources"

_SKIP_DIRS = {"__pycache__", ".venv"}
_MESHGEN_SKIP_TOP = {"__pycache__", ".venv", "cache", "reference_data"}
_MAX_NONPY_BYTES = 1_000_000  # meshgen 中 >1MB 的非 .py 文件视为数据/文档，不进包

# 资源包的 __init__.py 壳（rmtree 重建时写入，保证包可导入）。
# [EN] The __init__.py shell re-created after the stage dir is wiped.
_INIT_PY = '''"""WW3Tool runtime resources (pip install layout).

Build-time staged resources (params.yml / public / meshgen / requirements).
"""

from pathlib import Path

__all__ = ["resource_root", "is_packaged_root"]


def resource_root() -> Path:
    """Return this resource package's root directory."""
    return Path(__file__).resolve().parent


def is_packaged_root() -> bool:
    """True when this package carries the staged resources."""
    return (Path(__file__).resolve().parent / "params.yml").is_file()
'''


def _walk_copy(src_root: Path, rel_dir: str, skip_top: set[str] | None = None) -> None:
    src = src_root / rel_dir
    if not src.is_dir():
        return
    for dirpath, dirnames, filenames in os.walk(src):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        if skip_top and dirpath == str(src):
            dirnames[:] = [d for d in dirnames if d not in skip_top]
        for fn in filenames:
            if fn == ".DS_Store":
                continue
            p = Path(dirpath) / fn
            try:
                if p.stat().st_size > _MAX_NONPY_BYTES and p.suffix != ".py":
                    continue
            except OSError:
                continue
            tgt = _STAGE / rel_dir / p.relative_to(src)
            tgt.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, tgt)


def _stage_resources() -> None:
    # 非仓库根（例如从 sdist 解压后资源已在包内）时直接跳过，保持幂等。
    if not _ROOT.joinpath("params.yml").is_file():
        return
    if _STAGE.is_dir():
        shutil.rmtree(_STAGE)
    _STAGE.mkdir(parents=True, exist_ok=True)
    (_STAGE / "__init__.py").write_text(_INIT_PY, encoding="utf-8")

    shutil.copy2(_ROOT / "params.yml", _STAGE / "params.yml")
    req_src = _ROOT / "src" / "requirements.txt"
    if req_src.is_file():
        tgt = _STAGE / "src" / "requirements.txt"
        tgt.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(req_src, tgt)

    for rel in (
        "public/languages",
        "public/7.14_nml",
        "public/6.07_nml",
        "public/globe_picker",
        "public/scripts",
    ):
        _walk_copy(_ROOT, rel)

    # public/resource 只取 logo.png（README 媒体图等不进包）
    logo = _ROOT / "public" / "resource" / "logo.png"
    if logo.is_file():
        tgt = _STAGE / "public" / "resource" / "logo.png"
        tgt.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(logo, tgt)

    _walk_copy(_ROOT, "meshgen", skip_top=_MESHGEN_SKIP_TOP)


_stage_resources()

_readme = _ROOT / "public" / "packaging" / "PYPI_README.md"

setup(
    name="ww3tool",
    version="0.1.2",
    description=(
        "WW3Tool - WAVEWATCH III workflow toolkit "
        "(CLI / Shell REPL / Desktop GUI / MCP server)"
    ),
    long_description=_readme.read_text(encoding="utf-8") if _readme.is_file() else "",
    long_description_content_type="text/markdown",
    requires_python=">=3.9",
    install_requires=[
        "numpy",
        "netCDF4",
        "pandas",
        "matplotlib",
        "cartopy",
        "Pillow",
        "scipy",
        "scikit-image",
        "opencv-python",
        "paramiko",
        "requests",
        "PyYAML",
        "pyfiglet",
    ],
    extras_require={
        "gui": [
            "PyQt6",
            "PyQt6-WebEngine",
            "PyQt6-Fluent-Widgets",
        ],
        "dev": ["pytest"],
    },
    entry_points={"console_scripts": ["ww3tool=run:main"]},
    py_modules=["run"],
    packages=[
        "ww3tool_resources",
        "workflows",
        "workflows.support",
        "workflows.application",
        "workflows.infrastructure",
        "workflows.domain",
        "workflows.interfaces",
        "workflows.infrastructure.plot",
        "workflows.infrastructure.forcing",
        "workflows.infrastructure.ww3",
        "workflows.infrastructure.local",
        "workflows.infrastructure.adapters",
        "workflows.infrastructure.grid_visualization",
        "workflows.infrastructure.remote",
        "desktop",
        "desktop.view_models",
        "desktop.components",
        "desktop.steps",
        "desktop.windows",
    ],
    package_dir={
        "ww3tool_resources": "src/ww3tool_resources",
        "workflows": "src/workflows",
        "desktop": "src/desktop",
    },
    package_data={"ww3tool_resources": ["**/*"]},
    include_package_data=False,
)
