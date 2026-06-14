"""按区域范围推荐网格间距/分辨率参数（与界面无关的纯逻辑）。

被三种使用方式共享：桌面 GUI、交互式 shell、无界面 CLI。给定网格类型与经纬度
范围框，按区域较大边长（km）分档返回推荐参数。区域越大，间距越粗。

[EN] Grid spacing/resolution recommendations from domain extent (UI-independent).

Shared by the desktop GUI, the interactive shell and the headless CLI. Given a
mesh type and a lon/lat box, returns recommended spacing parameters scaled by
the domain's larger dimension in km. Larger domains → coarser spacing.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

# 分档表自上而下匹配，取首个满足 ``span >= 阈值`` 的档位。
# [EN] Tiers are matched top-down; the first tier whose threshold the span meets is used.

# (min_span_km, hmax, hshr, hmin, dhdx) — 非结构网格间距，单位 km
_UNST_TIERS: list[tuple[float, float, float, float, float]] = [
    (4000.0, 100.0, 25.0, 5.0, 0.08),
    (1500.0, 60.0, 15.0, 3.0, 0.07),
    (500.0, 30.0, 8.0, 2.0, 0.06),
    (150.0, 15.0, 4.0, 1.0, 0.05),
    (0.0, 8.0, 2.0, 0.5, 0.05),
]

# (min_span_km, dx=dy 度) — 结构化网格分辨率
_STRUCT_TIERS: list[tuple[float, float]] = [
    (4000.0, 0.5),
    (1500.0, 0.25),
    (500.0, 0.1),
    (150.0, 0.05),
    (0.0, 0.02),
]

# (min_span_km, n_levels) — SMC 细化层数
_SMC_TIERS: list[tuple[float, int]] = [
    (2000.0, 4),
    (800.0, 3),
    (0.0, 2),
]


def extent_km(lon: list[float], lat: list[float]) -> float:
    """区域经/纬两个方向中较大边长（km，经向按纬度做 cos 修正）。

    [EN] Larger of the domain's lon/lat dimensions, in km (cosine-corrected lon).
    """
    mean_lat = (lat[0] + lat[1]) / 2.0
    lat_km = abs(lat[1] - lat[0]) * 111.0
    lon_km = abs(lon[1] - lon[0]) * 111.0 * max(0.05, math.cos(math.radians(mean_lat)))
    return max(lat_km, lon_km)


def _fmt(value: float) -> str:
    """无多余零的紧凑数字文本。[EN] Compact numeric text without trailing zeros."""
    return f"{value:g}"


@dataclass(frozen=True)
class GridParamRecommendation:
    """一次推荐结果。

    - ``mesh_type``：``structured`` / ``smc`` / ``unstructured``
    - ``span_km``：区域较大边长（km）
    - ``section``：写回 ``grid`` 段时的子小节（``outer`` / ``smc`` / ``unstructured``）
    - ``values``：叶子键 → 推荐值（已格式化字符串）

    [EN] One recommendation. ``section`` is the ``grid`` subsection to persist under;
    ``values`` maps leaf keys to formatted recommended values.
    """

    mesh_type: str
    span_km: float
    section: str
    values: dict[str, str]

    def values_text(self) -> str:
        """如 ``hmax=15, hmin=1, hshr=4, dhdx=0.05``。"""
        return ", ".join(f"{k}={v}" for k, v in self.values.items())


def recommend_grid_params(
    mesh_type: Optional[str], lon: list[float], lat: list[float]
) -> Optional[GridParamRecommendation]:
    """按网格类型与经纬度范围返回推荐参数；范围无效（退化为点/线）时返回 ``None``。

    [EN] Recommend params for the given mesh type and lon/lat box; returns ``None``
    when the extent is invalid (degenerates to a point/line).
    """
    if lon[0] == lon[1] or lat[0] == lat[1]:
        return None

    span = extent_km(lon, lat)

    if mesh_type == "unstructured":
        hmax, hshr, hmin, dhdx = next(
            (t[1], t[2], t[3], t[4]) for t in _UNST_TIERS if span >= t[0]
        )
        values = {
            "hmax": _fmt(hmax),
            "hmin": _fmt(hmin),
            "hshr": _fmt(hshr),
            "dhdx": _fmt(dhdx),
        }
        return GridParamRecommendation("unstructured", span, "unstructured", values)

    if mesh_type == "smc":
        n_levels = next(t[1] for t in _SMC_TIERS if span >= t[0])
        return GridParamRecommendation("smc", span, "smc", {"n_levels": str(n_levels)})

    # 默认按结构化处理 [EN] default to structured
    res = next(t[1] for t in _STRUCT_TIERS if span >= t[0])
    return GridParamRecommendation(
        "structured", span, "outer", {"dx": _fmt(res), "dy": _fmt(res)}
    )
