"""嵌套网格工作目录下的 level0…levelN 子目录发现。

[EN] Discover nested grid level subdirectories (level0…levelN) under a workdir.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

_LEVEL_DIR_RE = re.compile(r"^level\d+$")


def list_nested_level_entries(workdir: str | Path) -> list[tuple[Path, int]]:
    """返回 ``[(path, index), ...]``，按 level 序号升序（level0 最粗）。

    [EN] Return ``[(path, index), ...]`` sorted by level index in ascending
    order (level0 is the coarsest).
    """
    root = Path(workdir)
    try:
        names = os.listdir(root)
    except OSError:
        return []
    entries = [
        (root / name, int(name[5:]))
        for name in names
        if _LEVEL_DIR_RE.match(name) and (root / name).is_dir()
    ]
    entries.sort(key=lambda item: item[1])
    return entries


def list_nested_level_paths(workdir: str | Path) -> list[Path]:
    return [path for path, _ in list_nested_level_entries(workdir)]


def list_nested_level_names(workdir: str | Path) -> list[str]:
    return [path.name for path, _ in list_nested_level_entries(workdir)]


def finest_nested_level_name(workdir: str | Path) -> str | None:
    entries = list_nested_level_entries(workdir)
    return entries[-1][0].name if entries else None


def outer_nested_level_path(workdir: str | Path) -> Path | None:
    entries = list_nested_level_entries(workdir)
    return entries[0][0] if entries else None


def is_nested_workdir(workdir: str | Path) -> bool:
    return bool(list_nested_level_entries(workdir))
