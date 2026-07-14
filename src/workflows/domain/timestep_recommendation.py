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
CFL_FACTORS = {
    "safe": 0.9,
    "fast": 1.05,
    "faster": 1.15,
}


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


def resolve_cfl_factor(mode: str = "safe", explicit: Optional[float] = None) -> float:
    """Return the CFL multiplier used for timestep recommendation.

    ``safe`` preserves the historical 0.9 setting. ``fast`` and ``faster`` are
    intentionally more aggressive options for throughput-sensitive reruns.
    """
    if explicit is not None:
        factor = float(explicit)
    else:
        key = str(mode or "safe").strip().lower()
        if key not in CFL_FACTORS:
            raise ValueError(f"unknown CFL mode: {mode}")
        factor = CFL_FACTORS[key]
    if factor <= 0:
        raise ValueError("CFL factor must be positive")
    if factor > 1.25:
        raise ValueError("CFL factor above 1.25 is too aggressive for automatic recommendation")
    return factor


def grid_spacing_meters(dx_deg: float, dy_deg: float, lat_deg: float) -> float:
    """Minimum grid spacing in meters at the given latitude."""
    dx_m = abs(dx_deg) * METERS_PER_DEGREE_LAT * math.cos(math.radians(lat_deg))
    dy_m = abs(dy_deg) * METERS_PER_DEGREE_LAT
    return min(dx_m, dy_m)


def compute_tcfl(dxy_m: float, freq1: float, cg_max: Optional[float] = None) -> float:
    """CFL 时间 = Δx / Cg_max。

    默认 Cg_max 用深水群速度 ``G/(4π·FREQ1)``（与 ``dxy_m·FREQ1·4π/G`` 等价）；
    若传入 ``cg_max``（按地形由色散关系算出的域内最大群速度），则用它。

    [EN] CFL time = Δx / Cg_max.

    By default Cg_max uses the deep-water group velocity ``G/(4π·FREQ1)``
    (equivalent to ``dxy_m·FREQ1·4π/G``). If ``cg_max`` is passed (the domain
    maximum group velocity computed from the dispersion relation over bathymetry),
    it is used instead.
    """
    if dxy_m <= 0:
        raise ValueError("grid spacing must be positive")
    if freq1 <= 0:
        raise ValueError("FREQ1 must be positive")
    if cg_max is not None:
        if cg_max <= 0:
            raise ValueError("cg_max must be positive")
        return dxy_m / cg_max
    return dxy_m * freq1 * 4.0 * PI / G


def deep_water_cg(freq1: float) -> float:
    """最低频波的深水群速度（m/s）：Cg = G/(4π·FREQ1)。

    [EN] Deep-water group velocity (m/s) of the lowest-frequency wave: Cg = G/(4π·FREQ1).
    """
    if freq1 <= 0:
        raise ValueError("FREQ1 must be positive")
    return G / (4.0 * PI * freq1)


def group_velocity(freq: float, depth: float) -> float:
    """线性波理论群速度（m/s）：频率 ``freq``(Hz) 的波在水深 ``depth``(m) 处的 Cg。

    解色散关系 ``ω² = g·k·tanh(k·h)`` 求 k，再 ``Cg = (C/2)(1 + 2kh/sinh(2kh))``。
    中等水深的 Cg 会超过深水值（峰值约在 0.2~0.4 倍深水波长处）。

    [EN] Linear wave theory group velocity (m/s): Cg of a wave with frequency ``freq`` (Hz)
    at water depth ``depth`` (m).

    Solves the dispersion relation ``ω² = g·k·tanh(k·h)`` for k, then
    ``Cg = (C/2)(1 + 2kh/sinh(2kh))``.
    Cg in intermediate depths can exceed the deep-water value (peak around 0.2–0.4 deep-water wavelengths).
    """
    if freq <= 0 or depth <= 0:
        return 0.0
    omega = 2.0 * PI * freq
    k = omega * omega / G  # 深水初值
    # [EN] Deep-water initial guess for k
    for _ in range(60):
        kh = k * depth
        if kh > 50.0:  # 深水：tanh≈1，初值即解
            # [EN] Deep water: tanh≈1, so the initial guess is already the solution
            break
        th = math.tanh(kh)
        f = G * k * th - omega * omega
        df = G * (th + kh * (1.0 - th * th))
        if df == 0.0:
            break
        k_new = k - f / df
        if k_new <= 0.0:
            k_new = 0.5 * k
        if abs(k_new - k) <= 1e-12 * k_new:
            k = k_new
            break
        k = k_new
    kh = k * depth
    c = omega / k
    ratio = 0.0 if kh > 25.0 else 2.0 * kh / math.sinh(2.0 * kh)
    return 0.5 * c * (1.0 + ratio)


def max_group_velocity(
    freq1: float, depth_min: float, depth_max: float, samples: int = 80
) -> float:
    """域内 FREQ1 波的最大群速度（m/s）：在 [depth_min, depth_max] 上扫描取最大。

    捕捉中等水深处超过深水值的峰值；以深水群速度为下限兜底（全深水域即回到深水值）。

    [EN] Maximum group velocity (m/s) of the FREQ1 wave within the domain, obtained by scanning [depth_min, depth_max].

    Captures the peak that exceeds the deep-water value in intermediate depths;
    lower-bounded by the deep-water group velocity (returns to deep-water value in fully deep domains).
    """
    if freq1 <= 0:
        raise ValueError("FREQ1 must be positive")
    lo = max(1.0, float(depth_min))
    hi = max(lo, float(depth_max))
    best = deep_water_cg(freq1)
    for i in range(samples + 1):
        h = lo * (hi / lo) ** (i / samples)  # 对数等距
        cg = group_velocity(freq1, h)
        if cg > best:
            best = cg
    return best


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

    [EN] Minimum grid spacing (m) for the CFL formula, by mesh type.

    Returns ``(dxy_m, reason)``: ``reason`` is empty on success; on failure ``dxy_m`` is ``None``
    and ``reason`` is an error token (``"need_grid"`` / ``"need_hmin"``).

    - Structured / SMC: finest cell = base spacing ``dx/dy`` (degrees), converted to meters by latitude.
      (SMC multi-resolution only coarsens selected cells upward; the base is the finest, so it follows the structured path.)
    - Unstructured: finest edge = ``hmin`` (km), converted directly to meters without degree→meter conversion.
    """
    if mesh_type == "unstructured":
        if hmin_km is None or hmin_km <= 0:
            return None, "need_hmin"
        return float(hmin_km) * 1000.0, ""
    # 结构化与 SMC：度制基准格距
    # [EN] Structured and SMC: base spacing in degrees
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
    cg_max: Optional[float] = None,
) -> TimestepRecommendation:
    """Return WW3-compatible timestep seconds from a lon/lat grid and FREQ1.

    ``cg_max`` 可选：按地形由色散关系算出的域内最大群速度（见 ``max_group_velocity``）；
    省略则用深水近似。

    [EN] Return WW3-compatible timestep seconds from a lon/lat grid and FREQ1.

    ``cg_max`` is optional: the domain maximum group velocity computed from the dispersion
    relation over bathymetry (see ``max_group_velocity``); omitted means deep-water approximation.
    """
    dxy_m = grid_spacing_meters(dx_deg, dy_deg, lat_deg)
    return recommend_timesteps_from_spacing(
        dxy_m=dxy_m,
        freq1=freq1,
        has_strong_current=has_strong_current,
        dtmin=dtmin,
        cfl_factor=cfl_factor,
        cg_max=cg_max,
    )


def recommend_timesteps_from_spacing(
    *,
    dxy_m: float,
    freq1: float,
    has_strong_current: bool = False,
    dtmin: int = 15,
    cfl_factor: float = 0.9,
    cg_max: Optional[float] = None,
) -> TimestepRecommendation:
    """Return WW3-compatible timestep seconds from an explicit min spacing (m).

    Mesh-type-agnostic core: callers resolve ``dxy_m`` via ``cfl_spacing_meters``
    (structured/SMC from degree spacing, unstructured from ``hmin``).
    ``cg_max`` 可选：按地形修正的最大群速度，省略则用深水近似。

    [EN] Return WW3-compatible timestep seconds from an explicit minimum spacing (m).

    Mesh-type-agnostic core: callers resolve ``dxy_m`` via ``cfl_spacing_meters``
    (structured/SMC from degree spacing, unstructured from ``hmin``).
    ``cg_max`` is optional: bathymetry-corrected maximum group velocity; omitted means deep-water approximation.
    """
    tcfl = compute_tcfl(dxy_m, freq1, cg_max=cg_max)
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
