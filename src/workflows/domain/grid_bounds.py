"""Grid geographic bounds helpers (UI-independent).

[EN] Utilities for detecting and snapping lon/lat boxes to the canonical
global WW3 domain (-180~180, -90~90), and for deriving safe cartopy map extents.
"""

from __future__ import annotations

import math
from typing import Literal

GLOBAL_LON = (-180.0, 180.0)
GLOBAL_LAT = (-90.0, 90.0)
# reference_data 中 ETOPO/GEBCO 通常达不到精确的 ±180/±90（例如 etopo2 为 179.995/89.9973）。
# [EN] ETOPO/GEBCO in reference_data usually does not reach exact ±180/±90 (e.g. etopo2 ends at 179.995/89.9973).
BATHY_SAFE_LON = (-180.0, 179.995)
BATHY_SAFE_LAT = (-90.0, 89.9973)
NEAR_GLOBAL_TOLERANCE_DEG = 5.0
# Mercator 在极高纬度会产生 Inf；cartopy 预览图在纬度接近 ±90° 时改用 PlateCarree。
# [EN] Mercator produces Inf near the poles; cartopy previews switch to PlateCarree when latitudes approach ±90°.
MERCATOR_MAX_ABS_LAT = 85.0

MapProjectionName = Literal["mercator", "plate_carree"]


def lon_span_deg(lon: list[float] | tuple[float, float]) -> float:
    """Longitude span in degrees, including dateline-crossing boxes."""
    lon_min, lon_max = float(lon[0]), float(lon[1])
    if lon_min > lon_max:
        return (180.0 - lon_min) + (lon_max + 180.0)
    return abs(lon_max - lon_min)


def is_global_bounds(
    lon: list[float] | tuple[float, float],
    lat: list[float] | tuple[float, float],
    *,
    eps: float = 1e-3,
) -> bool:
    """Return True when bounds already match the canonical global domain."""
    lon_min, lon_max = float(lon[0]), float(lon[1])
    lat_min, lat_max = float(lat[0]), float(lat[1])
    return (
        abs(lon_min - GLOBAL_LON[0]) <= eps
        and abs(lon_max - GLOBAL_LON[1]) <= eps
        and abs(lat_min - GLOBAL_LAT[0]) <= eps
        and abs(lat_max - GLOBAL_LAT[1]) <= eps
    )


def is_near_global_bounds(
    lon: list[float] | tuple[float, float],
    lat: list[float] | tuple[float, float],
    *,
    tolerance_deg: float = NEAR_GLOBAL_TOLERANCE_DEG,
) -> bool:
    """Return True when bounds are within ``tolerance_deg`` of global coverage."""
    if is_global_bounds(lon, lat):
        return False
    lon_span = lon_span_deg(lon)
    lat_span = abs(float(lat[1]) - float(lat[0]))
    min_lon_span = 360.0 - 2.0 * tolerance_deg
    min_lat_span = 180.0 - 2.0 * tolerance_deg
    return lon_span >= min_lon_span and lat_span >= min_lat_span


def clamp_regional_bounds_to_bathy_safe(
    west: float,
    east: float,
    south: float,
    north: float,
) -> tuple[float, float, float, float]:
    """Inset regional edges that exceed typical bathymetry NetCDF coverage."""
    west = max(BATHY_SAFE_LON[0], min(west, east))
    east = min(BATHY_SAFE_LON[1], max(west, east))
    south = max(BATHY_SAFE_LAT[0], min(south, north))
    north = min(BATHY_SAFE_LAT[1], max(south, north))
    return west, east, south, north


def normalize_longitude(lon: float) -> float:
    """Wrap longitude into ``[-180, 180]``."""
    lon = float(lon)
    wrapped = ((lon + 180.0) % 360.0) - 180.0
    # Keep +180 representable when input was exactly 180
    if wrapped == -180.0 and lon > 0:
        return 180.0
    return wrapped


def point_in_lon_lat_bounds(
    lon: float,
    lat: float,
    *,
    lon_min: float,
    lon_max: float,
    lat_min: float,
    lat_max: float,
    eps: float = 1e-6,
) -> bool:
    """Test whether a geographic point lies inside a lon/lat box (supports global + dateline)."""
    lat_v = float(lat)
    if lat_v < float(lat_min) - eps or lat_v > float(lat_max) + eps:
        return False
    lon_v = normalize_longitude(lon)
    west = normalize_longitude(lon_min)
    east = normalize_longitude(lon_max)
    if (
        is_global_bounds((west, east), (lat_min, lat_max), eps=0.05)
        or is_near_global_bounds((west, east), (lat_min, lat_max))
        or lon_span_deg((west, east)) >= 300.0
    ):
        return GLOBAL_LON[0] - eps <= lon_v <= GLOBAL_LON[1] + eps
    if west <= east:
        return west - eps <= lon_v <= east + eps
    return lon_v >= west - eps or lon_v <= east + eps


def map_aspect_wh_from_extent(extent: list[float] | tuple[float, float, float, float]) -> float:
    """根据 ``[west, east, south, north]`` 估算地图宽高比（用于对话框尺寸）。

    [EN] Estimate map width/height ratio from ``[west, east, south, north]`` (used for dialog sizing).
    """
    west, east, south, north = (float(extent[0]), float(extent[1]), float(extent[2]), float(extent[3]))
    lat_center = 0.5 * (south + north)
    lon_span = max(east - west, 1e-6)
    lat_span = max(north - south, 1e-6)
    cos_ref = max(abs(math.cos(math.radians(lat_center))), 0.08)
    return float(max(0.2, min((lon_span * cos_ref) / lat_span, 14.0)))


def regional_map_extent(
    lon: list[float] | tuple[float, float],
    lat: list[float] | tuple[float, float],
    *,
    padding_deg: float | None = None,
    padding_frac: float = 0.1,
    min_padding_deg: float = 2.0,
) -> dict[str, object]:
    """为 cartopy 预览/选点地图计算安全的显示范围与投影。

    近全球域返回 PlateCarree + 全球范围；区域域在 Mercator 安全纬度内优先 Mercator，
    否则退回 PlateCarree。避免 ``set_extent`` 纬度超出 Mercator 极限导致 NaN/Inf。

    [EN] Compute a safe display extent and projection for cartopy preview/point-selection maps.

    Near-global domains return PlateCarree + global extent; regional domains prefer Mercator
    when within safe Mercator latitudes, otherwise fall back to PlateCarree. Prevents NaN/Inf
    from ``set_extent`` latitudes beyond the Mercator limit.
    """
    west = float(min(lon[0], lon[1]))
    east = float(max(lon[0], lon[1]))
    south = float(min(lat[0], lat[1]))
    north = float(max(lat[0], lat[1]))
    lon_sp = lon_span_deg((west, east))
    lat_sp = abs(north - south)

    if (
        is_global_bounds((west, east), (south, north), eps=0.05)
        or is_near_global_bounds((west, east), (south, north))
        or lon_sp >= 300.0
        or lat_sp >= 150.0
    ):
        extent = [GLOBAL_LON[0], GLOBAL_LON[1], GLOBAL_LAT[0], GLOBAL_LAT[1]]
        return {
            "extent": extent,
            "central_lon": 0.0,
            "projection": "plate_carree",
            "aspect_wh": map_aspect_wh_from_extent(extent),
        }

    if padding_deg is None:
        pad_lon = max(min_padding_deg, padding_frac * lon_sp)
        pad_lat = max(min_padding_deg, padding_frac * lat_sp)
    else:
        pad_lon = pad_lat = float(padding_deg)

    west_p = max(GLOBAL_LON[0], west - pad_lon)
    east_p = min(GLOBAL_LON[1], east + pad_lon)
    south_p = max(GLOBAL_LAT[0], south - pad_lat)
    north_p = min(GLOBAL_LAT[1], north + pad_lat)

    mercator_safe = (
        south_p >= -MERCATOR_MAX_ABS_LAT
        and north_p <= MERCATOR_MAX_ABS_LAT
        and lon_sp < 300.0
        and lat_sp < 150.0
    )
    if mercator_safe:
        projection: MapProjectionName = "mercator"
        extent = [west_p, east_p, south_p, north_p]
    else:
        projection = "plate_carree"
        south_p = max(GLOBAL_LAT[0], south_p)
        north_p = min(GLOBAL_LAT[1], north_p)
        extent = [west_p, east_p, south_p, north_p]

    central_lon = 0.5 * (extent[0] + extent[1])
    return {
        "extent": extent,
        "central_lon": central_lon,
        "projection": projection,
        "aspect_wh": map_aspect_wh_from_extent(extent),
    }


def regional_map_extent_from_boxes(
    boxes: list[dict[str, float]],
    *,
    padding_deg: float | None = None,
    padding_frac: float = 0.1,
    min_padding_deg: float = 2.0,
) -> dict[str, object] | None:
    """由多个 ``lon_min/lon_max/lat_min/lat_max`` 框的并集计算地图显示参数。

    [EN] Compute map display parameters from the union of multiple ``lon_min/lon_max/lat_min/lat_max`` boxes.
    """
    if not boxes:
        return None
    west = min(box["lon_min"] for box in boxes)
    east = max(box["lon_max"] for box in boxes)
    south = min(box["lat_min"] for box in boxes)
    north = max(box["lat_max"] for box in boxes)
    return regional_map_extent(
        [west, east],
        [south, north],
        padding_deg=padding_deg,
        padding_frac=padding_frac,
        min_padding_deg=min_padding_deg,
    )
