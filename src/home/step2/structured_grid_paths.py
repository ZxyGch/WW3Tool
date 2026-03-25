# WW3 structured grid description (output of write_ww3meta → grid.meta).
from __future__ import annotations

import glob
import os

from .rect_grid_desc_parse import parse_rect_grid_description


def _is_ww3_full_nml_file(path: str) -> bool:
    """Older full ``grid.nml`` with ``&DEPTH_NML`` etc."""
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            chunk = f.read(16000)
    except OSError:
        return False
    return "&DEPTH_NML" in chunk or "$ Define grid" in chunk


def structured_grid_desc_path(folder: str) -> str | None:
    if not folder or not os.path.isdir(folder):
        return None
    gm = os.path.join(folder, "grid.meta")
    if os.path.isfile(gm) and parse_rect_grid_description(gm):
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
    if os.path.isfile(os.path.join(folder, "grid.meta")) and parse_rect_grid_description(
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
