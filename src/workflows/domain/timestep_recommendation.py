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
from typing import Optional

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


def cfl_spacing_meters(
    mesh_type: Optional[str],
    *,
    dx_deg: Optional[float] = None,
    dy_deg: Optional[float] = None,
    lat_deg: float = 0.0,
    hmin_km: Optional[float] = None,
) -> tuple[Optional[float], str]:
    """按网格类型返回 CFL 所需的最小网格尺度（米）。

    返回 ``(dxy_m, reason)``：成功时 ``reason`` 为空串；失败时 ``dxy_m`` 为 ``None`` 且
    ``reason`` 为错误标识（``"need_grid"`` / ``"need_hmin"``）。

    - 结构化 / SMC：最细 cell = 基准格距 ``dx/dy``（度），按纬度换算成米。
      （SMC 的多分辨率只把部分 cell 往粗合并，base 即最细，故与结构化同源。）
    - 非结构化：最细边 = ``hmin``（km），直接换算成米，不经过度→米。

    [EN] Minimum grid spacing (m) for the CFL formula, by mesh type. SMC's base
    cell is its finest cell (coarsening only merges cells upward), so it shares
    the structured path; unstructured uses ``hmin`` (km) directly.
    """
    if mesh_type == "unstructured":
        if hmin_km is None or hmin_km <= 0:
            return None, "need_hmin"
        return float(hmin_km) * 1000.0, ""
    # 结构化与 SMC：度制基准格距
    if not dx_deg or not dy_deg or dx_deg <= 0 or dy_deg <= 0:
        return None, "need_grid"
    return grid_spacing_meters(float(dx_deg), float(dy_deg), lat_deg), ""


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
    """Return WW3-compatible timestep seconds from a lon/lat grid and FREQ1."""
    dxy_m = grid_spacing_meters(dx_deg, dy_deg, lat_deg)
    return recommend_timesteps_from_spacing(
        dxy_m=dxy_m,
        freq1=freq1,
        has_strong_current=has_strong_current,
        dtmin=dtmin,
        cfl_factor=cfl_factor,
    )


def recommend_timesteps_from_spacing(
    *,
    dxy_m: float,
    freq1: float,
    has_strong_current: bool = False,
    dtmin: int = 15,
    cfl_factor: float = 0.9,
) -> TimestepRecommendation:
    """Return WW3-compatible timestep seconds from an explicit min spacing (m).

    Mesh-type-agnostic core: callers resolve ``dxy_m`` via ``cfl_spacing_meters``
    (structured/SMC from degree spacing, unstructured from ``hmin``)."""
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
