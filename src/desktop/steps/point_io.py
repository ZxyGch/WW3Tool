"""第三步点位文件解析与网格边界读取（纯逻辑，无 Qt 依赖）。

- ``parse_spectral_points_file`` / ``parse_track_points_file``：复刻 src ``step3_service``
  的文本格式解析，返回点位列表与跳过告警。
- ``grid_bounds``：按第二步网格类型读取经纬度包围盒，供导入/录入时的范围校验。
  结构化/嵌套读 ``grid.meta``（RECT），非结构读 ``grid.ww3``；与 src
  ``_read_grid_meta_bounds`` 一致，不跨类型回退。

[EN] Step 3 point file parsing and grid boundary reading (pure logic, no Qt dependency).

- ``parse_spectral_points_file`` / ``parse_track_points_file``: replicate src ``step3_service``
  text format parsing, returning point lists and skip warnings.
- ``grid_bounds``: read lon/lat bounding box by step 2 grid type for range validation during
  import/entry. Structured/nested reads ``grid.meta`` (RECT), unstructured reads ``grid.ww3``;
  consistent with src ``_read_grid_meta_bounds``, no cross-type fallback.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

# [EN] ``lon lat 'name'``: longitude, latitude, optional quoted name.
# ``lon lat 'name'``：经度、纬度、可带引号的名称。
_SPECTRAL_LINE = re.compile(r"(\S+)\s+(\S+)\s+['\"]?([^'\"]+)['\"]?")

LON_RANGE = (-180.0, 180.0)
LAT_RANGE = (-90.0, 90.0)


def _in_global_range(lon: float, lat: float) -> bool:
    return LON_RANGE[0] <= lon <= LON_RANGE[1] and LAT_RANGE[0] <= lat <= LAT_RANGE[1]


def _in_bounds(lon: float, lat: float, bounds: dict | None) -> bool:
    if not bounds:
        return True
    return (
        bounds["lon_min"] <= lon <= bounds["lon_max"]
        and bounds["lat_min"] <= lat <= bounds["lat_max"]
    )


def parse_spectral_points_file(
    path: str | Path, *, bounds: dict | None = None
) -> tuple[list[dict[str, Any]], list[str]]:
    # [EN] Parse spectral points file: each line ``lon lat 'name'``, ``#`` comments and blank lines skipped, stops at ``STOPSTRING``.
    #
    # [EN] Returns ``(points, warnings)``; ``points`` elements are ``{"lon", "lat", "name"}``.
    # [EN] Points outside global lon/lat range or (when given) grid bounding box are skipped and logged to ``warnings``.
    """解析谱点文件：每行 ``lon lat 'name'``，``#`` 注释与空行跳过，遇 ``STOPSTRING`` 停止。

    返回 ``(points, warnings)``；``points`` 元素为 ``{"lon", "lat", "name"}``。
    超出全局经纬度范围或（给定时）网格包围盒的点会被跳过并记入 ``warnings``。
    """
    points: list[dict[str, Any]] = []
    warnings: list[str] = []
    with open(path, "r", encoding="utf-8", errors="ignore") as handle:
        for line_num, raw in enumerate(handle, 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            match = _SPECTRAL_LINE.match(line)
            if not match:
                warnings.append(f"第 {line_num} 行：格式不正确，已跳过")
                continue
            name = match.group(3).strip().strip("'\"")
            if name.upper() == "STOPSTRING":
                break
            try:
                lon = float(match.group(1))
                lat = float(match.group(2))
            except ValueError:
                warnings.append(f"第 {line_num} 行：无法解析经纬度，已跳过")
                continue
            if not _in_global_range(lon, lat):
                warnings.append(f"第 {line_num} 行：经纬度超出范围，已跳过")
                continue
            if not _in_bounds(lon, lat, bounds):
                warnings.append(f"第 {line_num} 行：点位不在网格范围内，已跳过")
                continue
            points.append({"lon": lon, "lat": lat, "name": name})
    return points, warnings


def parse_track_points_file(
    path: str | Path, *, bounds: dict | None = None
) -> tuple[list[dict[str, Any]], list[str]]:
    # [EN] Parse track points file: each line ``date time lon lat [name...]`` (e.g. ``20250101 000000 120 20 T1``).
    #
    # [EN] Returns ``(points, warnings)``; ``points`` elements are ``{"datetime", "lon", "lat", "name"}``,
    # [EN] ``datetime`` formatted as ``"YYYYMMDD HHMMSS"``.
    """解析航迹文件：每行 ``date time lon lat [name…]``（如 ``20250101 000000 120 20 T1``）。

    返回 ``(points, warnings)``；``points`` 元素为 ``{"datetime", "lon", "lat", "name"}``，
    ``datetime`` 形如 ``"YYYYMMDD HHMMSS"``。
    """
    points: list[dict[str, Any]] = []
    warnings: list[str] = []
    with open(path, "r", encoding="utf-8", errors="ignore") as handle:
        for line_num, raw in enumerate(handle, 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 4:
                warnings.append(f"第 {line_num} 行：列数不足（需 date time lon lat），已跳过")
                continue
            date_str, time_str = parts[0], parts[1]
            name = " ".join(parts[4:]) if len(parts) > 4 else f"Track{line_num}"
            try:
                lon = float(parts[2])
                lat = float(parts[3])
            except ValueError:
                warnings.append(f"第 {line_num} 行：无法解析经纬度，已跳过")
                continue
            if not _in_global_range(lon, lat):
                warnings.append(f"第 {line_num} 行：经纬度超出范围，已跳过")
                continue
            if not _in_bounds(lon, lat, bounds):
                warnings.append(f"第 {line_num} 行：点位不在网格范围内，已跳过")
                continue
            points.append(
                {"datetime": f"{date_str} {time_str}", "lon": lon, "lat": lat, "name": name}
            )
    return points, warnings


def _bounds_from_mesh(lon, lat) -> dict | None:
    import numpy as np

    if lon is None or lat is None:
        return None
    return {
        "lon_min": float(np.min(lon)),
        "lon_max": float(np.max(lon)),
        "lat_min": float(np.min(lat)),
        "lat_max": float(np.max(lat)),
    }


def _structured_dir_bounds(directory: Path) -> dict | None:
    from workflows.infrastructure.grid_visualization.rect_grid_desc_parse import (
        structured_lon_lat_mesh,
    )
    from workflows.infrastructure.grid_visualization.structured_grid_paths import (
        structured_grid_desc_path,
    )

    desc = structured_grid_desc_path(str(directory))
    if desc is None:
        return None
    lon, lat = structured_lon_lat_mesh(desc)
    return _bounds_from_mesh(lon, lat)


def _union(a: dict | None, b: dict | None) -> dict | None:
    if not a or not b:
        return None
    return {
        "lon_min": min(a["lon_min"], b["lon_min"]),
        "lon_max": max(a["lon_max"], b["lon_max"]),
        "lat_min": min(a["lat_min"], b["lat_min"]),
        "lat_max": max(a["lat_max"], b["lat_max"]),
    }


def grid_bounds(workdir: str | Path, mesh_type: str, grid_type: str) -> dict | None:
    # [EN] Read lon/lat bounding box by grid type; returns ``None`` when parsing fails or type does not support bounding box validation.
    #
    # [EN] - structured / nested: read RECT range from ``grid.meta`` (nested takes coarse/fine union).
    # [EN] - unstructured: read range from ``grid.ww3`` nodes.
    # [EN] - smc: returns ``None`` (only global lon/lat validation).
    """按网格类型读取经纬度包围盒；无法解析或类型不支持包围盒校验时返回 ``None``。

    - structured / 嵌套：从 ``grid.meta`` 取 RECT 范围（嵌套取 coarse/fine 并集）。
    - unstructured：从 ``grid.ww3`` 节点取范围。
    - smc：返回 ``None``（仅做全局经纬度校验）。
    """
    directory = Path(workdir)
    if not directory.is_dir():
        return None
    if mesh_type == "unstructured":
        from workflows.infrastructure.grid_visualization.worker import (
            read_gmsh_ww3,
            unst_extent_from_xy,
        )

        ww3 = directory / "grid.ww3"
        if not ww3.is_file():
            return None
        try:
            xy, _depth, _ect = read_gmsh_ww3(str(ww3))
        except Exception:
            return None
        lon_min, lon_max, lat_min, lat_max = unst_extent_from_xy(xy, margin_deg=0.0)
        return {"lon_min": lon_min, "lon_max": lon_max, "lat_min": lat_min, "lat_max": lat_max}
    if mesh_type == "structured":
        if grid_type == "nested":
            return _union(
                _structured_dir_bounds(directory / "coarse"),
                _structured_dir_bounds(directory / "fine"),
            )
        return _structured_dir_bounds(directory)
    return None
