"""统一绘图输出目录：``{workdir}/photo/<subdir>/``。

[EN] Unified plotting output directory: ``{workdir}/photo/<subdir>/``.
"""

from __future__ import annotations

import glob
import os
import shutil
from typing import List

PHOTO_ROOT = "photo"

SUBDIR_WIND_FIELD = "wind_field"
SUBDIR_DIRECTIONAL_SPECTRUM = "directional_spectrum"
SUBDIR_WAVE_HEIGHT = "wave_height"
SUBDIR_WIND_SWELL = "wind_swell"
SUBDIR_WAVE_HEIGHT_CONTOUR = "wave_height_contour"
SUBDIR_WAVE_HEIGHT_VIDEO = "wave_height_video"
SUBDIR_JASON3_SATELLITE = "jason3_satellite"
SUBDIR_JASON3_FIT = "jason3_fit"
SUBDIR_NDBC_FIT = "ndbc_fit"


def photo_subdir(base_folder: str, subdir: str) -> str:
    """返回 ``{base_folder}/photo/{subdir}`` 路径（不创建目录）。

    [EN] Return the ``{base_folder}/photo/{subdir}`` path (does not create the directory).
    """
    return os.path.join(base_folder, PHOTO_ROOT, subdir)


def prepare_photo_subdir(base_folder: str, subdir: str) -> str:
    """清空并重建 ``photo/<subdir>``，返回其绝对路径。

    [EN] Clear and rebuild ``photo/<subdir>``, returning its absolute path.
    """
    path = photo_subdir(base_folder, subdir)
    if os.path.isdir(path):
        for name in os.listdir(path):
            item = os.path.join(path, name)
            try:
                if os.path.isdir(item) and not os.path.islink(item):
                    shutil.rmtree(item)
                else:
                    os.remove(item)
            except OSError:
                pass
    os.makedirs(path, exist_ok=True)
    return path


def collect_photo_files(base_folder: str, subdir: str, pattern: str = "*") -> List[str]:
    """收集 ``photo/<subdir>`` 下匹配 glob 模式的文件路径。

    [EN] Collect file paths under ``photo/<subdir>`` matching the glob pattern.
    """
    path = photo_subdir(base_folder, subdir)
    if not os.path.isdir(path):
        return []
    return sorted(glob.glob(os.path.join(path, pattern)))
