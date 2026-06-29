"""SMC 底网格 RECT 与强迫场裁剪范围对齐工具。

``ww3_prnc`` 会把风/流/水位插值到 ``ww3_rect_geo`` 定义的**整块**底网格上，
而 SMC 胞元对齐到全球 SMC 经纬步长后，该范围往往比第二步 ``grid.lon/lat`` 或
``regional_bounds`` 外扩约 0.03°–0.25°（尤其东侧受 ERA5 0.25° 格点量化影响）。
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import netCDF4 as nc

DEFAULT_FORCING_SNAP_DEG = 0.25


def read_ww3_rect_geo(work_dir: str | Path) -> dict[str, float] | None:
    """从工作目录 ``grid.json`` 读取 ``ww3_rect_geo``。"""
    path = Path(work_dir).expanduser() / "grid.json"
    if not path.is_file():
        return None
    try:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None
    geo = data.get("ww3_rect_geo")
    if not isinstance(geo, dict):
        return None
    try:
        return {
            "lon_west": float(geo["lon_west"]),
            "lon_east": float(geo["lon_east"]),
            "lat_south": float(geo["lat_south"]),
            "lat_north": float(geo["lat_north"]),
        }
    except (KeyError, TypeError, ValueError):
        return None


def recommended_forcing_bbox(
    rect_geo: dict[str, float],
    *,
    snap_deg: float = DEFAULT_FORCING_SNAP_DEG,
    margin_deg: float = 0.0,
) -> list[float]:
    """由 ``ww3_rect_geo`` 计算强迫场裁剪框 ``[west, east, south, north]``。

    向外取整到 ``snap_deg``（默认 ERA5 0.25°），保证裁剪后 NetCDF 仍含覆盖 RECT 的格点。
    """
    west = float(rect_geo["lon_west"]) - margin_deg
    east = float(rect_geo["lon_east"]) + margin_deg
    south = float(rect_geo["lat_south"]) - margin_deg
    north = float(rect_geo["lat_north"]) + margin_deg
    if snap_deg > 0:
        west = snap_deg * math.floor(west / snap_deg)
        east = snap_deg * math.ceil(east / snap_deg)
        south = snap_deg * math.floor(south / snap_deg)
        north = snap_deg * math.ceil(north / snap_deg)
    return [west, east, south, north]


def forcing_nc_lonlat_bounds(nc_path: str | Path) -> tuple[float, float, float, float] | None:
    """返回 NetCDF 的 (lon_min, lon_max, lat_min, lat_max)。"""
    try:
        with nc.Dataset(str(nc_path), "r") as ds:
            lon_vn = lat_vn = None
            for nm in ("longitude", "lon", "LONGITUDE", "LON"):
                if nm in ds.variables and int(ds.variables[nm].ndim) == 1:
                    lon_vn = nm
                    break
            for nm in ("latitude", "lat", "LATITUDE", "LAT"):
                if nm in ds.variables and int(ds.variables[nm].ndim) == 1:
                    lat_vn = nm
                    break
            if lon_vn is None or lat_vn is None:
                return None
            lon = np.asarray(ds.variables[lon_vn][:], dtype=float)
            lat = np.asarray(ds.variables[lat_vn][:], dtype=float)
            return float(lon.min()), float(lon.max()), float(lat.min()), float(lat.max())
    except Exception:
        return None


def forcing_covers_rect(
    forcing_bounds: tuple[float, float, float, float],
    rect_geo: dict[str, float],
    *,
    eps: float = 0.01,
) -> bool:
    """风场/流场范围是否覆盖 SMC RECT 地理包络。"""
    wlo, whi, wla, wlz = forcing_bounds
    lon_w = float(rect_geo["lon_west"])
    lon_e = float(rect_geo["lon_east"])
    lat_s = float(rect_geo["lat_south"])
    lat_n = float(rect_geo["lat_north"])
    return not (
        wlo > lon_w + eps
        or whi < lon_e - eps
        or wla > lat_s + eps
        or wlz < lat_n - eps
    )
