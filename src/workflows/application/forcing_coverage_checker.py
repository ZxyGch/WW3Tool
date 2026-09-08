"""强迫场覆盖范围检查工具。

检查强迫场文件的经纬度范围是否覆盖网格范围，以及时间范围是否满足要求。
供 GUI 和 CLI 共用。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from ..support.translations import tr
from ..support.logging import CoreLogger
from ..domain.config_models import PipelineConfig
from ..domain.forcing_fields import Step2Files
from ..domain.grid_bounds import longitude_interval_contains


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
    issue_type: str = "insufficient"
    error: Optional[str] = None


def check_lonlat_coverage(
    grid_lon_west: float,
    grid_lon_east: float,
    grid_lat_south: float,
    grid_lat_north: float,
    forcing_paths: dict,
    field_names: dict,
    *, variable_names: Optional[dict] = None,
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

    for key in ("wind", "current", "level", "ice"):
        path = forcing_paths.get(key)
        if not path:
            continue
        try:
            names = (variable_names or {}).get(key, {})
            bounds = read_wind_bounds(
                path, continuous_longitude=True,
                longitude_name=names.get("longitude"), latitude_name=names.get("latitude"),
            )

            # 覆盖检查容差：0.001°（≈100m）处理 float32 精度误差
            # [EN] 0.001° tolerance (~100m) for float32 precision
            EPS = 0.001

            # 纬度不做标准化（始终 -90~90）
            lat_ok = (bounds.lat_min - EPS) <= grid_lat_south and (bounds.lat_max + EPS) >= grid_lat_north

            lon_ok = longitude_interval_contains(
                bounds.lon_min, bounds.lon_max, grid_lon_west, grid_lon_east, eps=EPS,
            )

            if not (lon_ok and lat_ok):
                issues.append(
                    ForcingCoverageIssue(
                        field_name=field_names.get(key, key),
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
                    field_name=field_names.get(key, key),
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
    *, time_names: Optional[dict] = None,
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

    # 按完整时刻比较，避免同日 06 时起始的数据覆盖被误判为包含 00 时。
    start = _requested_time(requested_start)
    end = _requested_time(requested_end)
    if start > end:
        raise ValueError("WW3 开始时间不能晚于结束时间")
    issues = []
    for key in ("wind", "current", "level", "ice"):
        path = forcing_paths.get(key)
        if not path:
            continue
        try:
            time_range = read_wind_time_range(path, time_name=(time_names or {}).get(key))
            time_start = time_range.start_time or _requested_time(time_range.start_date)
            time_end = time_range.end_time or _requested_time(time_range.end_date)
            if time_start > start or time_end < end:
                issues.append(
                    TimeRangeIssue(
                        field_name=field_names.get(key, key),
                        field_key=key,
                        path=path,
                        time_start=time_start,
                        time_end=time_end,
                        requested_start=requested_start,
                        requested_end=requested_end,
                    )
                )
        except Exception as exc:
            issues.append(TimeRangeIssue(
                field_name=field_names.get(key, key), field_key=key, path=str(path),
                time_start="", time_end="", requested_start=requested_start,
                requested_end=requested_end, issue_type="read_failed", error=str(exc),
            ))

    return issues


def _requested_time(value: str) -> str:
    """将请求日期规范为 YYYYMMDD HHMMSS，并校验日历日期。"""
    text = str(value).strip()
    if len(text) == 8:
        text += " 000000"
    return datetime.strptime(text, "%Y%m%d %H%M%S").strftime("%Y%m%d %H%M%S")


def validate_ww3_forcing_time(
    config: PipelineConfig, files: Step2Files, logger: CoreLogger, *, allow_remote: bool = True,
) -> None:
    """GUI、CLI 共用时间检查；本地场读取失败或覆盖不足时阻止生成或运行。"""
    from ..infrastructure.forcing.forcing_manifest import load_manifest

    manifest = load_manifest(str(config.workdir.path))
    paths, names, time_names = {}, {}, {}
    for key in ("wind", "current", "level", "ice"):
        path = getattr(files, key, None)
        remote_path = config.forcing.remote_paths.get(key)
        if not path:
            path = remote_path or getattr(config.forcing, key, None)
        if not path:
            continue
        # 服务器专用路径不能在客户端冒充已通过检查；输出明确的待校验提示。
        if remote_path and str(path) == str(remote_path) and not Path(path).is_file() and allow_remote:
            logger.log(tr(
                "forcing_time_remote_unchecked",
                "⚠️ {field} 为服务器路径，本地未校验时间覆盖，请在服务器准备算例时校验：{path}",
            ).format(field=key, path=path))
            continue
        paths[key] = str(path)
        names[key] = tr(f"step2_field_{key}", {"wind": "风场", "current": "流场", "level": "水位场", "ice": "海冰场"}[key])
        entry = manifest.get(key, {})
        if remote_path == str(path):
            custom = config.forcing.custom.get(key)
            time_names[key] = custom.time if custom else None
        elif entry.get("file") == Path(path).name:
            time_names[key] = entry.get("time")
        elif getattr(config.forcing, key, None) == Path(path):
            custom = config.forcing.custom.get(key)
            time_names[key] = custom.time if custom else None
    issues = check_time_range_coverage(
        config.ww3.start_date, config.ww3.end_date, paths, names, time_names=time_names,
    )
    if issues:
        details = []
        for issue in issues:
            if issue.issue_type == "read_failed":
                details.append(f"• {issue.field_name}：{issue.path}（{issue.error}）")
            else:
                details.append(f"• {issue.field_name}：{issue.path}\n"
                               f"  {issue.time_start} → {issue.time_end}\n"
                               f"  WW3：{issue.requested_start} → {issue.requested_end}")
        raise ValueError(tr(
            "forcing_time_validation_failed",
            "强迫场时间覆盖检查未通过：\n{details}",
        ).format(details="\n".join(details)))
