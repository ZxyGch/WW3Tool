from __future__ import annotations

import sys
from pathlib import Path


PYSMCS_DIR = Path(__file__).resolve().parents[1] / "SMCGTools" / "PySMCs"
sys.path.insert(0, str(PYSMCS_DIR))

from regional_bounds import outward_aligned_window


def test_regional_window_expands_outward() -> None:
    istart, iexpnd, jstart, jexpnd = outward_aligned_window(
        127.99,
        27.196,
        139.672,
        34.869,
        lon0=-180.0,
        lat0=-90.0,
        dlon=1.0 / 30.0,
        dlat=1.0 / 30.0,
        mfct=1,
        merg=1,
    )

    west = -180.0 + istart / 30.0
    east = -180.0 + (istart + iexpnd) / 30.0
    south = -90.0 + jstart / 30.0
    north = -90.0 + (jstart + jexpnd) / 30.0
    assert west <= 127.99
    assert east >= 139.672
    assert south <= 27.196
    assert north >= 34.869


def test_aligned_bounds_do_not_gain_an_extra_cell() -> None:
    assert outward_aligned_window(
        10.0,
        -20.0,
        14.0,
        -16.0,
        lon0=0.0,
        lat0=-90.0,
        dlon=0.5,
        dlat=0.5,
        mfct=2,
        merg=2,
    ) == (20, 8, 140, 8)
