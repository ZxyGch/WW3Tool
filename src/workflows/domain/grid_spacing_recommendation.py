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
# [EN] (min_span_km, hmax, hshr, hmin, dhdx) — unstructured mesh spacing, in km
_UNST_TIERS: list[tuple[float, float, float, float, float]] = [
    (4000.0, 100.0, 25.0, 5.0, 0.08),
    (1500.0, 60.0, 15.0, 3.0, 0.07),
    (500.0, 30.0, 8.0, 2.0, 0.06),
    (150.0, 15.0, 4.0, 1.0, 0.05),
    (0.0, 8.0, 2.0, 0.5, 0.05),
]

# (min_span_km, dx=dy 度) — 结构化网格分辨率
# [EN] (min_span_km, dx=dy in degrees) — structured grid resolution
_STRUCT_TIERS: list[tuple[float, float]] = [
    (4000.0, 0.5),
    (1500.0, 0.25),
    (500.0, 0.1),
    (150.0, 0.05),
    (0.0, 0.02),
]

# (min_span_km, n_levels) — SMC 细化层数
# [EN] (min_span_km, n_levels) — SMC refinement levels
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
        """如 ``hmax=15, hmin=1, hshr=4, dhdx=0.05``。

        [EN] e.g. ``hmax=15, hmin=1, hshr=4, dhdx=0.05``.
        """
        return ", ".join(f"{k}={v}" for k, v in self.values.items())


def _pick_tier(tiers: list, span: float, offset: int = 0):
    """按 span 匹配首个满足条件的档位，再用 offset 偏移（正=更粗，负=更细）。

    tiers 从最粗（index 0）到最细（index N-1）排列，所以 ``offset > 0``
    需要 *减小* index 才能更粗；超出边界时截断到最近有效档。

    [EN] Match the first tier whose threshold the span meets, then shift by
    ``offset`` (positive → coarser = lower index, negative → finer = higher
    index). Clamped to valid range.
    """
    matched = 0
    for i, t in enumerate(tiers):
        if span >= t[0]:
            matched = i
            break
    # offset > 0 → coarser → lower index; offset < 0 → finer → higher index
    shifted = max(0, min(len(tiers) - 1, matched - offset))
    return tiers[shifted]


def recommend_grid_params(
    mesh_type: Optional[str],
    lon: list[float],
    lat: list[float],
    *,
    offset: int = 0,
) -> Optional[GridParamRecommendation]:
    """按网格类型与经纬度范围返回推荐参数；范围无效（退化为点/线）时返回 ``None``。

    ``offset`` 可在自动匹配的基础上偏移档位：``+1`` 更粗，``-1`` 更细，
    超出边界时截断到最粗/最细档。

    [EN] Recommend params for the given mesh type and lon/lat box; returns ``None``
    when the extent is invalid (degenerates to a point/line).
    ``offset`` shifts the matched tier: ``+1`` coarser, ``-1`` finer, clamped.
    """
    if lon[0] == lon[1] or lat[0] == lat[1]:
        return None

    span = extent_km(lon, lat)

    if mesh_type == "unstructured":
        tier = _pick_tier(_UNST_TIERS, span, offset)
        hmax, hshr, hmin, dhdx = tier[1], tier[2], tier[3], tier[4]
        values = {
            "hmax": _fmt(hmax),
            "hmin": _fmt(hmin),
            "hshr": _fmt(hshr),
            "dhdx": _fmt(dhdx),
        }
        return GridParamRecommendation("unstructured", span, "unstructured", values)

    if mesh_type == "smc":
        tier = _pick_tier(_SMC_TIERS, span, offset)
        return GridParamRecommendation("smc", span, "smc", {"n_levels": str(tier[1])})

    # 默认按结构化处理 [EN] default to structured
    tier = _pick_tier(_STRUCT_TIERS, span, offset)
    return GridParamRecommendation(
        "structured", span, "outer", {"dx": _fmt(tier[1]), "dy": _fmt(tier[1])}
    )
