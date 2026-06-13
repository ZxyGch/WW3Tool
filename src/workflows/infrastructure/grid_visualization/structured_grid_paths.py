"""结构化 WW3 网格描述文件路径解析。

``write_ww3meta`` 产出 ``grid.meta`` 等描述文件；本模块在工作目录内按优先级
定位可用于可视化与复制的网格描述路径，并列出需随案例拷贝的 basename 列表。
"""
from __future__ import annotations

import glob
import os

from .rect_grid_desc_parse import parse_structured_grid_description


def _is_ww3_full_nml_file(path: str) -> bool:
    """判断是否为含 ``&DEPTH_NML`` 等段的完整 legacy ``grid.nml``。"""
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            chunk = f.read(16000)
    except OSError:
        return False
    return "&DEPTH_NML" in chunk or "$ Define grid" in chunk


def structured_grid_desc_path(folder: str) -> str | None:
    """返回目录内首选的网格描述文件绝对路径，无法解析时返回 ``None``。

    优先级：可解析的 ``grid.meta`` → 完整 ``grid.nml`` → ``ww3_grid.nml.grid``
    → 任意 ``ww3_grid.nml.*`` → 原始 ``grid.meta``。
    """
    if not folder or not os.path.isdir(folder):
        return None
    gm = os.path.join(folder, "grid.meta")
    if os.path.isfile(gm) and parse_structured_grid_description(gm):
        return gm
    gn = os.path.join(folder, "grid.nml")
    if os.path.isfile(gn) and _is_ww3_full_nml_file(gn):
        return gn
    preferred = os.path.join(folder, "ww3_grid.nml.grid")
    if os.path.isfile(preferred):
        return preferred
    cands = sorted(glob.glob(os.path.join(folder, "ww3_grid.nml.*")))
    if cands:
        return cands[0]
    if os.path.isfile(gm):
        return gm
    return None


def structured_grid_desc_basenames_to_copy(folder: str) -> list[str]:
    """返回打包/同步工作目录时应复制的网格描述文件 basename 列表。"""
    if os.path.isfile(os.path.join(folder, "grid.meta")) and parse_structured_grid_description(
        os.path.join(folder, "grid.meta")
    ):
        return ["grid.meta"]
    gn = os.path.join(folder, "grid.nml")
    if os.path.isfile(gn) and _is_ww3_full_nml_file(gn):
        return ["grid.nml"]
    names = sorted({os.path.basename(p) for p in glob.glob(os.path.join(folder, "ww3_grid.nml.*"))})
    if names:
        return names
    if os.path.isfile(os.path.join(folder, "grid.meta")):
        return ["grid.meta"]
    return []
