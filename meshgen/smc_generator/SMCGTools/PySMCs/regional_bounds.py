"""Regional SMC index alignment shared by cell and boundary generation."""

from __future__ import annotations

import math


def outward_aligned_window(
    xstart: float,
    ystart: float,
    xend: float,
    yend: float,
    *,
    lon0: float,
    lat0: float,
    dlon: float,
    dlat: float,
    mfct: int,
    merg: int,
) -> tuple[int, int, int, int]:
    """Return ``istart, iexpnd, jstart, jexpnd`` covering the requested box."""
    istep = int(merg) * int(mfct)
    jstep = int(mfct)
    if istep <= 0 or jstep <= 0 or dlon <= 0.0 or dlat <= 0.0:
        raise ValueError("Regional SMC spacing and alignment factors must be positive")

    # Avoid adding a row when a coordinate is already on a grid line but its
    # floating-point representation lies infinitesimally to the other side.
    eps = 1.0e-10
    i0 = math.floor((float(xstart) - lon0) / (istep * dlon) + eps) * istep
    i1 = math.ceil((float(xend) - lon0) / (istep * dlon) - eps) * istep
    j0 = math.floor((float(ystart) - lat0) / (jstep * dlat) + eps) * jstep
    j1 = math.ceil((float(yend) - lat0) / (jstep * dlat) - eps) * jstep

    if i1 <= i0:
        i1 = i0 + istep
    if j1 <= j0:
        j1 = j0 + jstep
    return int(i0), int(i1 - i0), int(j0), int(j1 - j0)
