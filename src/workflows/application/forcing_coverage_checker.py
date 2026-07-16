"""强迫场覆盖范围检查工具。

检查强迫场文件的经纬度范围是否覆盖网格范围，以及时间范围是否满足要求。
供 GUI 和 CLI 共用。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from ..support.translations import tr


@dataclass
class ForcingCoverageIssue:
    """覆盖问题的数据模型。

    Attributes:
        field_name: 场名称（如"风场"）
        field_key: 场键（如"wind"）
        path: 文件路径
        issue_type: "insufficient" 或 "read_failed"
        bounds: 场的范围（仅当 issue_type="insufficient"）
        grid_lon: 网格经度范围 (west, east)
        grid_lat: 网格纬度范围 (south, north)
        error: 读取失败错误信息（仅当 issue_type="read_failed"）
    """

    field_name: str
    field_key: str
    path: str
    issue_type: str  # "insufficient" | "read_failed"
    bounds: Optional[object] = None
    grid_lon: Optional[Tuple[float, float]] = None
    grid_lat: Optional[Tuple[float, float]] = None
    error: Optional[str] = None


@dataclass
class TimeRangeIssue:
    """时间范围问题的数据模型。

    Attributes:
        field_name: 场名称
        field_key: 场键
        path: 文件路径
        time_start: 场开始时间
        time_end: 场结束时间
        requested_start: 请求的开始时间
        requested_end: 请求的结束时间
    """

    field_name: str
    field_key: str
    path: str
    time_start: str
    time_end: str
    requested_start: str
    requested_end: str


def _normalize_lon(lon: float) -> float:
    """将经度统一标准化到 [-180, 180) 口径。"""
    return ((lon + 180.0) % 360.0) - 180.0


def check_lonlat_coverage(
    grid_lon_west: float,
    grid_lon_east: float,
    grid_lat_south: float,
    grid_lat_north: float,
    forcing_paths: dict,
    field_names: dict,
) -> List[ForcingCoverageIssue]:
    """检查强迫场经纬度范围是否覆盖网格范围。

    Args:
        grid_lon_west/east: 网格西/东边界
        grid_lat_south/north: 网格南/北边界
        forcing_paths: {"wind": path, "current": path, ...}
        field_names: {"wind": "风场", "current": "流场", ...}

    Returns:
        覆盖问题列表，空列表表示全部通过。
    """
    from ..application.grid_tools import read_wind_bounds

    issues = []

    # 网格经度标准化到 [-180, 180)
    g_west = _normalize_lon(grid_lon_west)
    g_east = _normalize_lon(grid_lon_east)
    # 检测网格是否跨日界线：标准化后西界 > 东界 表示跨日界线
    grid_crosses_date_line = g_west > g_east

    for key in ("wind", "current", "level", "ice"):
        path = forcing_paths.get(key)
        if not path:
            continue
        try:
            bounds = read_wind_bounds(path)
            # 强迫场经度标准化到 [-180, 180)
            f_lon_min = _normalize_lon(bounds.lon_min)
            f_lon_max = _normalize_lon(bounds.lon_max)
            # 若标准化后 min > max（跨日界线文件），交换使之连续
            if f_lon_min > f_lon_max:
                f_lon_min, f_lon_max = f_lon_max, f_lon_min

            # 覆盖检查容差：0.001°（≈100m）处理 float32 精度误差
            # [EN] 0.001° tolerance (~100m) for float32 precision
            EPS = 0.001

            # 纬度不做标准化（始终 -90~90）
            lat_ok = (bounds.lat_min - EPS) <= grid_lat_south and (bounds.lat_max + EPS) >= grid_lat_north

            # 经度覆盖检查
            if grid_crosses_date_line:
                # 网格跨日界线 => 分 [g_west, 180) 和 [-180, g_east) 两段
                lon_ok = (f_lon_min - EPS) <= g_west and (f_lon_max + EPS) >= g_east
            else:
                lon_ok = (f_lon_min - EPS) <= g_west and (f_lon_max + EPS) >= g_east

            if not (lon_ok and lat_ok):
                issues.append(
                    ForcingCoverageIssue(
                        field_name=field_names[key],
                        field_key=key,
                        path=path,
                        issue_type="insufficient",
                        bounds=bounds,
                        grid_lon=(grid_lon_west, grid_lon_east),
                        grid_lat=(grid_lat_south, grid_lat_north),
                    )
                )
        except Exception as exc:
            issues.append(
                ForcingCoverageIssue(
                    field_name=field_names[key],
                    field_key=key,
                    path=path,
                    issue_type="read_failed",
                    error=str(exc),
                )
            )

    return issues


def check_time_range_coverage(
    requested_start: str,
    requested_end: str,
    forcing_paths: dict,
    field_names: dict,
) -> List[TimeRangeIssue]:
    """检查强迫场时间范围是否覆盖请求的时间范围。

    Args:
        requested_start/end: 请求的时间范围（YYYYMMDD 格式）
        forcing_paths: {"wind": path, ...}
        field_names: {"wind": "风场", ...}

    Returns:
        时间范围问题列表，空列表表示全部通过。
    """
    from ..application.grid_tools import read_wind_time_range

    issues = []
    for key in ("wind", "current", "level", "ice"):
        path = forcing_paths.get(key)
        if not path:
            continue
        try:
            time_start, time_end = read_wind_time_range(path)
            # 比较字符串（YYYYMMDD 格式可直接比较）
            if time_start > requested_start or time_end < requested_end:
                issues.append(
                    TimeRangeIssue(
                        field_name=field_names[key],
                        field_key=key,
                        path=path,
                        time_start=time_start,
                        time_end=time_end,
                        requested_start=requested_start,
                        requested_end=requested_end,
                    )
                )
        except Exception:
            # 读取失败不阻塞，只记录
            pass

    return issues
