"""WW3 TIMESTEPS_NML recommendations from grid spacing and spectrum FREQ1.

Uses the CFL formula documented in ``ww3_grid.nml``:

    Tcfl = DXY / (G / (FREQ1 * 4 * pi))
    DTXY ~= 0.9 * Tcfl
    DTMAX ~= 3 * DTXY
    DTKTH ~= DTMAX / 2   (no or light currents)
"""

from __future__ import annotations

import math
from dataclasses import dataclass

PI = math.pi
G = 9.8
METERS_PER_DEGREE_LAT = 111_320.0


@dataclass(frozen=True)
class TimestepRecommendation:
    """Recommended WW3 integration timesteps (seconds)."""

    tcfl: float
    dxy_m: float
    dtxy: int
    dtmax: int
    dtkth: int
    dtmin: int
    cfl_ratio: float


def grid_spacing_meters(dx_deg: float, dy_deg: float, lat_deg: float) -> float:
    """Minimum grid spacing in meters at the given latitude."""
    dx_m = abs(dx_deg) * METERS_PER_DEGREE_LAT * math.cos(math.radians(lat_deg))
    dy_m = abs(dy_deg) * METERS_PER_DEGREE_LAT
    return min(dx_m, dy_m)


def compute_tcfl(dxy_m: float, freq1: float) -> float:
    if dxy_m <= 0:
        raise ValueError("grid spacing must be positive")
    if freq1 <= 0:
        raise ValueError("FREQ1 must be positive")
    return dxy_m * freq1 * 4.0 * PI / G


def recommend_timesteps(
    *,
    dx_deg: float,
    dy_deg: float,
    freq1: float,
    lat_deg: float = 0.0,
    has_strong_current: bool = False,
    dtmin: int = 15,
    cfl_factor: float = 0.9,
) -> TimestepRecommendation:
    """Return WW3-compatible timestep seconds from grid and spectrum settings."""
    dxy_m = grid_spacing_meters(dx_deg, dy_deg, lat_deg)
    tcfl = compute_tcfl(dxy_m, freq1)
    dtxy = max(1, int(round(cfl_factor * tcfl)))
    dtmax = max(1, int(round(3.0 * dtxy)))
    if has_strong_current:
        dtkth = max(1, int(round(dtmax / 10.0)))
    else:
        dtkth = max(1, int(round(dtmax / 2.0)))
    dtmin_value = max(1, min(int(dtmin), dtmax))
    return TimestepRecommendation(
        tcfl=tcfl,
        dxy_m=dxy_m,
        dtxy=dtxy,
        dtmax=dtmax,
        dtkth=dtkth,
        dtmin=dtmin_value,
        cfl_ratio=dtxy / tcfl,
    )


def as_ww3_grid_parameters(rec: TimestepRecommendation) -> dict[str, str]:
    return {
        "TIMESTEPS%DTXY": str(rec.dtxy),
        "TIMESTEPS%DTMAX": str(rec.dtmax),
        "TIMESTEPS%DTKTH": str(rec.dtkth),
        "TIMESTEPS%DTMIN": str(rec.dtmin),
    }
