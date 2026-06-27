"""SMC open-boundary helpers for WW3 namelist sync.

WW3 ``NBISMC`` reads integer cell indices from BUNDY (``*Blst.dat`` style),
not the full boundary-cell table written by ``smcellbdy`` (``*Bdys.dat``).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

BUNDY_FILENAME = "grid_bundy.dat"
BOUNDARY_CELLS_FILENAME = "grid_boundary.dat"


def count_smc_bundy_points(work_dir: str | os.PathLike[str]) -> int:
    """Return the number of open-boundary cell indices in ``grid_bundy.dat``."""
    path = Path(work_dir) / BUNDY_FILENAME
    if not path.is_file() or path.stat().st_size <= 0:
        return 0
    count = 0
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                count += 1
    return count


def read_smc_n_levels(work_dir: str | os.PathLike[str]) -> int | None:
    """Read SMC refinement level from workdir ``grid.json`` / ``smc_grid.json``."""
    root = Path(work_dir)
    for name in ("grid.json", "smc_grid.json"):
        path = root / name
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        grid = data.get("grid") if isinstance(data, dict) else None
        if isinstance(grid, dict) and grid.get("n_levels") is not None:
            return int(grid["n_levels"])
    return None
