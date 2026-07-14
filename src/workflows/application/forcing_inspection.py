"""Step 2 强迫场文件只读检查用例。

读取已选 NetCDF 强迫场文件，输出文件大小、经纬度范围、分辨率与时间轴等
摘要信息，供 CLI 与桌面端在导入前预览数据质量。

流水线步骤：Step 2（强迫场准备）— 只读检查，不写入工作目录。

输入/输出
---------
- 输入：``Step2Files``（各场类型的文件路径映射）
- 输出：日志消息列表（``list[str]``），内容与桌面端 Step 2 概览面板一致

[EN] Step 2 forcing file read-only inspection use case.

Reads selected NetCDF forcing files and outputs summaries including file size,
lon/lat range, resolution, and time axis for CLI and desktop preview before import.

Pipeline step: Step 2 (forcing preparation) -- read-only inspection, no writes to workdir.

Input/Output
------------
- Input: ``Step2Files`` (file path mapping for each field type)
- Output: Log message list (``list[str]``), content matches desktop Step 2 overview panel
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..domain.forcing_fields import FORCING_FIELD_ORDER, ForcingField, Step2Files

from ..support.formatting import format_file_size
from ..support.logging import CoreLogger, LogCallback
from ..support.translations import tr


FIELD_TITLES = {
    ForcingField.WIND: ("step1_field_wind", "风场"),
    ForcingField.CURRENT: ("step1_field_current", "流场"),
    ForcingField.LEVEL: ("step1_field_level", "水位场"),
    ForcingField.ICE: ("step1_field_ice", "海冰场"),
}


def report_forcing_file_overviews(
    files: Step2Files,
    log: Optional[LogCallback] = None,
) -> list[str]:
    """为已选择的强迫场 NetCDF 文件生成概览报告。

    遍历风、流、水位、海冰四类场，对存在的文件依次输出元数据摘要。

    Args:
        files: 各强迫场类型对应的本地文件路径。
        log: 可选日志回调，用于实时输出。

    Returns:
        完整日志消息列表；若无已选文件则返回提示消息。

    [EN] Generate overview reports for selected forcing NetCDF files.
    Iterates over wind, current, water level, and ice fields, outputting metadata summaries for existing files.

    Args:
        files: Local file paths for each forcing field type.
        log: Optional log callback for real-time output.

    Returns:
        Complete log message list; returns a prompt message if no files are selected.
    """
    logger = CoreLogger(callback=log)
    selected = [
        (tr(*FIELD_TITLES[field]), Path(path))
        for field in FORCING_FIELD_ORDER
        if (path := files.get(field)) and Path(path).is_file()
    ]
    if not selected:
        logger.log(tr("no_field_files_msg", "⚠️ 没有已选择的场文件，请先选择场文件"))
        return list(logger.messages)

    for field_name, path in selected:
        _report_file_overview(field_name, path, logger)
    logger.log("=" * 70)
    return list(logger.messages)


def report_netcdf_file_overviews(
    paths: list[str] | tuple[str, ...],
    log: Optional[LogCallback] = None,
) -> list[str]:
    """为任意 NetCDF 文件列表生成概览报告。

    供工具页合并强迫场前查看所有输入文件信息；不要求文件已经归类为
    wind/current/level/ice。

    [EN] Generate overview reports for arbitrary lists of NetCDF files.

    Used by the tools page to inspect all input files before merging forcings; files do not need to
    be already classified as wind/current/level/ice.
    """
    logger = CoreLogger(callback=log)
    selected = [Path(path) for path in paths if path and Path(path).is_file()]
    if not selected:
        logger.log(tr("no_field_files_msg", "⚠️ 没有已选择的场文件，请先选择场文件"))
        return list(logger.messages)

    for path in selected:
        _report_file_overview(path.name, path, logger)
    logger.log("=" * 70)
    return list(logger.messages)


def _report_file_overview(field_name: str, path: Path, logger: CoreLogger) -> None:
    """输出单个 NetCDF 强迫场文件的详细概览。

    [EN] Output a detailed overview of a single NetCDF forcing file.
    """
    import numpy as np
    from netCDF4 import Dataset, num2date

    logger.log("")
    logger.log("=" * 70)
    logger.log(f"【{field_name}】")
    logger.log(tr("forcing_info_filename", "ℹ️ 文件名：{name}").format(name=path.name))
    try:
        logger.log(tr("forcing_info_filesize", "ℹ️ 文件大小：{size}").format(size=format_file_size(path.stat().st_size)))
    except OSError as exc:
        logger.log(tr("forcing_info_filesize_unreadable", "ℹ️ 文件大小：无法读取 ({error})").format(error=exc))

    try:
        with Dataset(str(path), "r") as dataset:
            lon = _first_variable(dataset, ("longitude", "lon", "Longitude", "LON"))
            lat = _first_variable(dataset, ("latitude", "lat", "Latitude", "LAT"))

            if lon is not None:
                lon_values = lon[:]
                logger.log(tr("forcing_info_lon_range", "ℹ️ 经度范围：{min:.6f}° ~ {max:.6f}°").format(min=float(np.min(lon_values)), max=float(np.max(lon_values))))
                _report_resolution(tr("forcing_info_lon_resolution", "ℹ️ 经度精度"), lon_values, logger, np)
            if lat is not None:
                lat_values = lat[:]
                logger.log(tr("forcing_info_lat_range", "ℹ️ 纬度范围：{min:.6f}° ~ {max:.6f}°").format(min=float(np.min(lat_values)), max=float(np.max(lat_values))))
                _report_resolution(tr("forcing_info_lat_resolution", "ℹ️ 纬度精度"), lat_values, logger, np)

            time_name, time_var = _first_named_variable(
                dataset,
                ("time", "Time", "TIME", "valid_time", "MT", "mt", "t"),
            )
            if time_var is None:
                logger.log(tr("forcing_info_time_var_missing", "⚠️ 时间范围：未找到时间变量"))
                return
            _report_time_metadata_warnings(str(path), time_name, logger)
            _report_time(time_name, time_var, logger, np, num2date)
    except Exception as exc:
        logger.log(tr("forcing_info_read_failed", "❌ 读取文件信息失败：{error}").format(error=exc))


def _report_resolution(label: str, values, logger: CoreLogger, np) -> None:
    """记录坐标轴相邻格点间的平均间距。

    [EN] Record the average spacing between adjacent grid points on a coordinate axis.
    """
    if len(values) <= 1:
        return
    differences = np.diff(values)
    if len(differences) > 0:
        logger.log(f"{label}：{float(np.mean(np.abs(differences))):.6f}°")


def _report_time_metadata_warnings(path: str, time_name: str, logger: CoreLogger) -> None:
    """检查 time 元数据是否满足 WW3 ww3_prnc 要求。

    [EN] Check whether the time metadata meets the WW3 ww3_prnc requirements.
    """
    from ..infrastructure.forcing.forcing_time_metadata import (
        audit_time_metadata_for_ww3,
        format_time_metadata_issue_logs,
    )

    issues = [
        issue
        for issue in audit_time_metadata_for_ww3(path, time_name=time_name)
        if issue.code not in {"nc_string_attr", "invalid_units"}
    ]
    if not issues:
        return
    logger.log(tr("forcing_time_metadata_warning_header", "⚠️ WW3 时间轴兼容性："))
    for line in format_time_metadata_issue_logs(issues):
        logger.log(f"  {line}")


def _report_time(name: str, variable, logger: CoreLogger, np, num2date) -> None:
    """解析并记录 NetCDF 时间变量的起止时刻、步数与平均间隔。

    [EN] Parse and record the start/end times, step count, and average interval of a NetCDF time variable.
    """
    try:
        units = getattr(variable, "units", None)
        if not units:
            values = variable[:]
            if len(values) > 0:
                logger.log(tr("forcing_info_time_range_no_units", "ℹ️ 时间范围：{start:.2f} ~ {end:.2f} (无单位)").format(start=float(np.min(values)), end=float(np.max(values))))
                logger.log(tr("forcing_info_time_steps", "ℹ️ 时间步数：{count}").format(count=len(values)))
            return

        calendar = getattr(variable, "calendar", "gregorian")
        times = num2date(variable[:], units, calendar=calendar)
        if hasattr(times, "compressed"):
            times = times.compressed()
        if isinstance(times, np.ndarray):
            times = times.ravel().tolist()
        elif not isinstance(times, (list, tuple)):
            times = [times]
        times = [item for item in times if hasattr(item, "strftime")]
        if not times:
            return

        logger.log(
            tr("forcing_info_time_range", "ℹ️ 时间范围：{start} ~ {end}").format(
                start=times[0].strftime("%Y-%m-%d %H:%M:%S"),
                end=times[-1].strftime("%Y-%m-%d %H:%M:%S"),
            )
        )
        logger.log(tr("forcing_info_time_steps", "ℹ️ 时间步数：{count}").format(count=len(times)))
        if len(times) > 1:
            intervals = [(times[index + 1] - times[index]).total_seconds() for index in range(len(times) - 1)]
            logger.log(tr("forcing_info_time_resolution", "ℹ️ 时间精度：{interval}").format(interval=_format_interval(float(np.mean(intervals)))))
        if name != "time":
            logger.log(tr("forcing_info_time_variable", "ℹ️ 使用时间变量：{name}").format(name=name))
    except Exception as exc:
        logger.log(tr("forcing_info_time_unparseable", "⚠️ 时间范围：无法解析 ({error})").format(error=exc))


def _first_variable(dataset, names: tuple[str, ...]):
    """按候选名称列表在 NetCDF 数据集中查找第一个存在的变量。

    [EN] Find the first existing variable in a NetCDF dataset by candidate name list.
    """
    for name in names:
        if name in dataset.variables:
            return dataset.variables[name]
    return None


def _first_named_variable(dataset, names: tuple[str, ...]):
    """按候选名称列表查找变量，返回 (变量名, 变量对象) 或 (None, None)。

    [EN] Find a variable by candidate name list, returning (variable name, variable object) or (None, None).
    """
    for name in names:
        if name in dataset.variables:
            return name, dataset.variables[name]
    return None, None


def _format_interval(seconds: float) -> str:
    """将秒数格式化为秒/分钟/小时/天的可读字符串。

    [EN] Format seconds into a human-readable string of seconds/minutes/hours/days.
    """
    if seconds < 60:
        return tr("time_seconds", "ℹ️ {value} 秒").format(value=f"{seconds:.0f}")
    if seconds < 3600:
        return tr("time_minutes", "ℹ️ {value} 分钟").format(value=f"{seconds / 60:.1f}")
    if seconds < 86400:
        return tr("time_hours", "ℹ️ {value} 小时").format(value=f"{seconds / 3600:.2f}")
    return tr("time_days", "ℹ️ {value} 天").format(value=f"{seconds / 86400:.2f}")
