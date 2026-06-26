"""Grid geographic bounds helpers (UI-independent).

[EN] Utilities for detecting and snapping lon/lat boxes to the canonical
global WW3 domain (-180~180, -90~90).
"""

from __future__ import annotations

GLOBAL_LON = (-180.0, 180.0)
GLOBAL_LAT = (-90.0, 90.0)
# reference_data 中 ETOPO/GEBCO 通常达不到精确的 ±180/±90（例如 etopo2 为 179.995/89.9973）。
BATHY_SAFE_LON = (-180.0, 179.995)
BATHY_SAFE_LAT = (-90.0, 89.9973)
NEAR_GLOBAL_TOLERANCE_DEG = 5.0


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
