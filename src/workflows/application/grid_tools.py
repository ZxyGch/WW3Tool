"""Step 2 网格只读工具用例。

提供风场边界读取、嵌套区域缩放、区域地图预览与网格可视化等纯读取/预览功能，
不写入工作目录。供桌面 ViewModel 与未来 CLI 检查命令复用。

流水线步骤：Step 2（网格配置与预览）— 辅助工具，非生成主流程。

输入/输出
---------
- 输入：``PipelineConfig``、风场 NetCDF 路径或 ``GridRegion``
- 输出：``GridBounds``、``GridPreviewResult``（图片路径与日志消息）

[EN] Step 2 grid read-only tool use cases.

Provides read-only/preview functionality including wind field bounds reading,
nested region scaling, area map preview, and grid visualization without writing
to the workdir. For reuse by desktop ViewModels and future CLI inspection commands.

Pipeline step: Step 2 (grid configuration and preview) -- auxiliary tools, not the main generation flow.

Input/Output
------------
- Input: ``PipelineConfig``, wind field NetCDF path or ``GridRegion``
- Output: ``GridBounds``, ``GridPreviewResult`` (image paths and log messages)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from collections.abc import Sequence
from typing import Optional

from ..domain.config_models import GridConfig, GridRegion, PipelineConfig
from ..support.logging import CoreLogger, LogCallback
from ..support.translations import tr


@dataclass(frozen=True)
class GridBounds:
    """从 NetCDF 风场文件解析出的地理边界。

    Attributes:
        lon_min: 最小经度（度）。
        lon_max: 最大经度（度）。
        lat_min: 最小纬度（度）。
        lat_max: 最大纬度（度）。
        source_path: 源文件的绝对路径。

    [EN] Geographic bounds parsed from a NetCDF wind field file.

    Attributes:
        lon_min: Minimum longitude (degrees).
        lon_max: Maximum longitude (degrees).
        lat_min: Minimum latitude (degrees).
        lat_max: Maximum latitude (degrees).
        source_path: Absolute path of the source file.
    """

    lon_min: float
    lon_max: float
    lat_min: float
    lat_max: float
    source_path: str = ""


@dataclass(frozen=True)
class WindTimeRange:
    """从 NetCDF 风场文件解析出的时间范围。

    Attributes:
        start_date: 首个时间点，``YYYYMMDD``。
        end_date: 最后一个时间点，``YYYYMMDD``。
        source_path: 源文件的绝对路径。

    [EN] Time range parsed from a NetCDF wind field file.

    Attributes:
        start_date: First time point, ``YYYYMMDD``.
        end_date: Last time point, ``YYYYMMDD``.
        source_path: Absolute path of the source file.
    """

    start_date: str
    end_date: str
    source_path: str = ""


@dataclass
class GridPreviewResult:
    """网格预览或可视化操作的返回结果。

    Attributes:
        images: 生成的预览图片绝对路径列表。
        title: 预览窗口标题（供 UI 使用）。
        messages: 执行过程中的日志消息。

    [EN] Return result of grid preview or visualization operation.

    Attributes:
        images: List of absolute paths of generated preview images.
        title: Preview window title (for UI use).
        messages: Log messages during execution.
    """

    images: list[str]
    title: str
    messages: list[str]


def read_wind_bounds(path: str | Path, log: Optional[LogCallback] = None) -> GridBounds:
    """从风场 NetCDF 文件读取经纬度范围。

    Args:
        path: 风场 NetCDF 文件路径。
        log: 可选日志回调。

    Returns:
        解析得到的 ``GridBounds``。

    Raises:
        RuntimeError: 文件不存在或未找到经度/纬度变量时。

    [EN] Read lon/lat range from a wind field NetCDF file.

    Args:
        path: Wind field NetCDF file path.
        log: Optional log callback.

    Returns:
        Parsed ``GridBounds``.

    Raises:
        RuntimeError: When file does not exist or lon/lat variables are not found.
    """
    import numpy as np
    from netCDF4 import Dataset

    logger = CoreLogger(callback=log)
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise RuntimeError(tr("step2_wind_file_not_found_path", "❌ 未找到风场文件：{path}").format(path=source))

    with Dataset(str(source), "r") as dataset:
        lon = _first_variable(dataset, ("longitude", "lon", "Longitude", "LON"))
        lat = _first_variable(dataset, ("latitude", "lat", "Latitude", "LAT"))
        if lon is None:
            raise RuntimeError(tr("step2_lon_var_not_found_simple", "❌ {file} 中未找到经度变量").format(file=source.name))
        if lat is None:
            raise RuntimeError(tr("step2_lat_var_not_found_simple", "❌ {file} 中未找到纬度变量").format(file=source.name))
        bounds = GridBounds(
            lon_min=float(np.min(lon[:])),
            lon_max=float(np.max(lon[:])),
            lat_min=float(np.min(lat[:])),
            lat_max=float(np.max(lat[:])),
            source_path=str(source),
        )
    logger.log(tr("step2_auto_load_range", "ℹ️ 已从 {filename} 自动加载经纬度范围").format(filename=source.name))
    return bounds


def read_wind_time_range(path: str | Path, log: Optional[LogCallback] = None) -> WindTimeRange:
    """从风场 NetCDF 文件读取时间范围。

    Args:
        path: 风场 NetCDF 文件路径。
        log: 可选日志回调。

    Returns:
        解析得到的 ``WindTimeRange``。

    Raises:
        RuntimeError: 文件不存在、未找到时间变量或时间变量无法转换时。

    [EN] Read time range from a wind field NetCDF file.

    Args:
        path: Wind field NetCDF file path.
        log: Optional log callback.

    Returns:
        Parsed ``WindTimeRange``.

    Raises:
        RuntimeError: When file does not exist, time variable not found, or time variable cannot be converted.
    """
    import numpy as np
    from netCDF4 import Dataset, num2date

    logger = CoreLogger(callback=log)
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise RuntimeError(tr("step2_wind_file_not_found_path", "❌ 未找到风场文件：{path}").format(path=source))

    with Dataset(str(source), "r") as dataset:
        time_var = _first_variable(dataset, ("time", "Time", "TIME", "valid_time", "MT", "mt", "t"))
        if time_var is None:
            raise RuntimeError(tr("step4_time_var_not_found_simple", "❌ {file} 中未找到时间变量").format(file=source.name))
        units = getattr(time_var, "units", None)
        if not units:
            raise RuntimeError(tr("step4_time_units_missing", "❌ {file} 中的时间变量没有 units 属性，无法转换时间").format(file=source.name))
        calendar = getattr(time_var, "calendar", "gregorian")
        try:
            times = num2date(time_var[:], units, calendar=calendar)
        except Exception as exc:
            raise RuntimeError(tr("step4_time_read_failed", "❌ 读取 {file} 时间失败：{error}").format(file=source.name, error=exc)) from exc
        if hasattr(times, "compressed"):
            times = times.compressed()
        if isinstance(times, np.ndarray):
            times = times.ravel().tolist()
        elif not isinstance(times, (list, tuple)):
            times = [times]
        times = [time for time in times if hasattr(time, "strftime")]
        if not times:
            raise RuntimeError(tr("step4_time_var_empty", "❌ {file} 中的时间变量为空").format(file=source.name))
        result = WindTimeRange(
            start_date=times[0].strftime("%Y%m%d"),
            end_date=times[-1].strftime("%Y%m%d"),
            source_path=str(source),
        )
    logger.log(tr("step4_time_range_loaded", "✅ 已从 {file} 读取时间范围：{start} → {end}").format(file=source.name, start=result.start_date, end=result.end_date))
    return result


def scale_nested_region(region: GridRegion, factor: float, *, expand: bool) -> GridRegion:
    """以区域中心为基准缩放嵌套网格范围，与桌面 Step 2 控件行为一致。

    Args:
        region: 当前外/内网格区域配置。
        factor: 嵌套收缩系数（须大于 0）。
        expand: ``True`` 扩大区域，``False`` 收缩区域。

    Returns:
        缩放后的新 ``GridRegion``（含更新后的 dx/dy 与 lon/lat）。

    Raises:
        ValueError: ``factor`` 不大于 0 时。

    [EN] Scale the nested grid region relative to the region center, consistent with desktop Step 2 controls.

    Args:
        region: Current outer/inner grid region config.
        factor: Nested contraction coefficient (must be > 0).
        expand: ``True`` to expand the region, ``False`` to shrink it.

    Returns:
        New scaled ``GridRegion`` (with updated dx/dy and lon/lat).

    Raises:
        ValueError: When ``factor`` is not greater than 0.
    """
    if factor <= 0:
        raise ValueError(tr("nested_factor_must_positive", "❌ 嵌套收缩系数必须大于 0"))
    multiplier = factor if expand else 1.0 / factor
    lon_center = (region.lon[0] + region.lon[1]) / 2
    lat_center = (region.lat[0] + region.lat[1]) / 2
    lon_half = abs(region.lon[1] - region.lon[0]) * multiplier / 2
    lat_half = abs(region.lat[1] - region.lat[0]) * multiplier / 2
    return GridRegion(
        dx=region.dx * multiplier,
        dy=region.dy * multiplier,
        lon=[lon_center - lon_half, lon_center + lon_half],
        lat=[lat_center - lat_half, lat_center + lat_half],
    )


def render_region_map(
    config: PipelineConfig,
    output_path: str | Path,
    log: Optional[LogCallback] = None,
) -> GridPreviewResult:
    """根据配置的外/内网格范围生成区域地图 PNG 预览。

    Args:
        config: 流水线配置（使用 ``config.grid`` 中的区域信息）。
        output_path: 输出 PNG 文件路径。
        log: 可选日志回调。

    Returns:
        含单张预览图路径与日志的 ``GridPreviewResult``。

    [EN] Generate a region map PNG preview based on the configured outer/inner grid extents.

    Args:
        config: Pipeline config (uses region info from ``config.grid``).
        output_path: Output PNG file path.
        log: Optional log callback.

    Returns:
        ``GridPreviewResult`` with a single preview image path and log.
    """
    from ..infrastructure.region_map_renderer import render_region_map_png

    logger = CoreLogger(callback=log)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    render_region_map_png(config.grid, output)
    if config.grid.grid_type == "nested" and config.grid.inner is not None:
        logger.log(tr("step2_nested_map_displayed", "✅ 已显示嵌套网格地图"))
    else:
        logger.log(
            tr(
                "step2_map_range_displayed",
                "ℹ️ 已显示地图范围: 经度 [{lon_min}, {lon_max}], 纬度 [{lat_min}, {lat_max}]",
            ).format(
                lon_min=f"{config.grid.outer.lon[0]:.2f}",
                lon_max=f"{config.grid.outer.lon[1]:.2f}",
                lat_min=f"{config.grid.outer.lat[0]:.2f}",
                lat_max=f"{config.grid.outer.lat[1]:.2f}",
            )
        )
    return GridPreviewResult(images=[str(output)], title=tr("step2_view_map", "查看地图"), messages=list(logger.messages))


def render_forcing_region_map(
    regions: Sequence[GridRegion],
    labels: Sequence[str],
    output_path: str | Path,
    log: Optional[LogCallback] = None,
) -> GridPreviewResult:
    """渲染最多四个强迫场文件的经纬度范围预览图。"""
    from ..infrastructure.region_map_renderer import render_region_map_png

    if not regions:
        raise RuntimeError(tr("step1_select_forcing_first", "请先选择至少一个强迫场文件"))
    logger = CoreLogger(callback=log)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    grid = GridConfig(
        mesh_type="structured",
        grid_type="nested" if len(regions) > 1 else "normal",
        outer=regions[0],
        inner=regions[-1] if len(regions) > 1 else None,
        nested_levels=list(regions),
    )
    render_region_map_png(grid, output, labels=labels)
    logger.log(tr("step1_forcing_map_displayed", "✅ 已显示强迫场范围地图"))
    return GridPreviewResult(images=[str(output)], title=tr("step2_view_map", "查看地图"), messages=list(logger.messages))


def visualize_grid(
    config: PipelineConfig,
    log: Optional[LogCallback] = None,
) -> GridPreviewResult:
    """对工作目录中已有的网格产物生成可视化图片。

    Args:
        config: 流水线配置（工作目录与网格类型）。
        log: 可选日志回调。

    Returns:
        含多张网格图路径与日志的 ``GridPreviewResult``。

    [EN] Generate visualization images for existing grid artifacts in the workdir.

    Args:
        config: Pipeline config (workdir and grid type).
        log: Optional log callback.

    Returns:
        ``GridPreviewResult`` with multiple grid image paths and log.
    """
    from ..infrastructure.adapters.grid_visualization_adapter import generate_grid_images

    logger = CoreLogger(callback=log)
    images = generate_grid_images(config, logger)
    logger.log(tr("step2_visualization_done", "✅ 网格可视化已生成"))
    return GridPreviewResult(images=images, title=tr("step2_visualize_grid_results", "ℹ️ 网格可视化结果"), messages=list(logger.messages))


def _first_variable(dataset, names: tuple[str, ...]):
    """按候选名称列表在 NetCDF 数据集中查找第一个存在的变量。

    [EN] Find the first existing variable in a NetCDF dataset by candidate name list.
    """
    for name in names:
        if name in dataset.variables:
            return dataset.variables[name]
    return None
