"""强迫场解析结果持久化（``forcing_manifest.json``）。

[EN] Forcing resolution persistence (``forcing_manifest.json``).

导入成功后在工作目录生成 ``forcing_manifest.json``，记录每个场使用的
文件与变量映射，使软件重启或直接执行第四步时无需再次猜测变量
（方案 §7）。该文件是程序生成的运行结果，不供用户手动编辑。

[EN] After a successful import, ``forcing_manifest.json`` is written in the
working directory recording the file and variable mapping per field, so the
software does not need to guess variables again after restart or when running
step four directly (spec §7). The file is program output, not meant for manual
editing.
"""

from __future__ import annotations

import json
import os
from typing import Dict, Optional

from ...domain.config_models import ResolvedForcingVariables

MANIFEST_FILENAME = "forcing_manifest.json"

# 清单项结构（方案 §7）：
# [EN] Manifest entry structure (spec §7):
# {
#   "wind": {
#     "file": "wind.nc",
#     "longitude": "XLONG",
#     "latitude": "XLAT",
#     "time": "time",
#     "variables": ["UGRD_10m", "VGRD_10m"],
#     "thickness": null
#   }
# }


def manifest_path(workdir: str) -> str:
    """工作目录中的 manifest 文件路径。

    [EN] Manifest file path inside the working directory.
    """
    return os.path.join(workdir, MANIFEST_FILENAME)


def load_manifest(workdir: Optional[str]) -> Dict[str, dict]:
    """读取 manifest；不存在或损坏时返回空字典。

    [EN] Load the manifest; returns an empty dict when missing or corrupt.
    """
    if not workdir:
        return {}
    path = manifest_path(workdir)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_manifest_entry(
    workdir: str,
    field: str,
    resolved: ResolvedForcingVariables,
    filename: str,
) -> bool:
    """写入（或合并更新）单个场的清单项。

    [EN] Write (or merge-update) one field's manifest entry.
    """
    if not workdir:
        return False
    data = load_manifest(workdir)
    data[field] = {
        "file": filename,
        "longitude": resolved.longitude,
        "latitude": resolved.latitude,
        "time": resolved.output_time or "time",
        "variables": list(resolved.components),
        "thickness": resolved.thickness,
    }
    try:
        with open(manifest_path(workdir), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except OSError:
        return False
