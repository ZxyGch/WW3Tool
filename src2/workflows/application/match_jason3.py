"""Jason-3 卫星有效波高（SWH）匹配与绘图用例。

将 WW3 模式输出与 Jason-3 沿轨观测进行时空匹配，或单独绘制 Jason-3 SWH 分布图，
供 CLI ``match-jason3`` / ``jason3-swh`` 命令与桌面后处理面板调用。

流水线步骤：后处理（Step 4 结果验证）— 卫星观测对比。

输入/输出
---------
- 输入：``PipelineConfig``（``plot.jason3.*`` 与结果目录）
- 输出：``Jason3Result``（输出目录、PNG 列表、成功标志与错误信息）
"""

from __future__ import annotations

import glob
import os
from ..support.process_worker import run_plot_worker
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from ..domain.config_models import PipelineConfig
from ..infrastructure.plot.photo_output import (
    SUBDIR_JASON3_FIT,
    SUBDIR_JASON3_SATELLITE,
    collect_photo_files,
    photo_subdir,
)
from ..support.logging import CoreLogger, LogCallback
from ..support.translations import tr


@dataclass
class Jason3Result:
    """Jason-3 匹配或 SWH 绘图操作的返回结果。

    Attributes:
        output_folder: 结果文件输出目录。
        image_files: 生成的 PNG 图片路径列表。
        messages: 执行过程中的日志消息。
        success: 操作是否成功完成。
        error: 失败时的错误描述；成功时为 ``None``。
    """

    output_folder: str
    image_files: List[str] = field(default_factory=list)
    messages: List[str] = field(default_factory=list)
    success: bool = True
    error: Optional[str] = None


def _resolve_result_folder(config: PipelineConfig) -> Path:
    """解析 WW3 结果目录：优先 ``plot.result_folder``，否则使用 ``workdir``。"""
    if config.plot.result_folder:
        return Path(config.plot.result_folder)
    return config.workdir.path


def _resolve_jason3_data_folder(
    config: PipelineConfig,
    override: Optional[str] = None,
) -> Optional[str]:
    """解析 Jason-3 本地数据目录：UI/CLI 覆盖 > params > JASON_PATH > 项目 jason3/。"""
    if override and os.path.isdir(override):
        return os.path.abspath(override)
    cfg = config.plot.jason3
    if cfg.data_folder and cfg.data_folder.is_dir():
        return str(cfg.data_folder)
    from ..infrastructure.runtime_config import ensure_project_data_dir

    return ensure_project_data_dir("JASON_PATH", "jason3")


def _resolve_jason3_lon_lat(
    config: PipelineConfig,
    override: Optional[List[float]] = None,
) -> Optional[List[float]]:
    """解析 Jason-3 绘图/下载区域：UI/CLI 覆盖 > plot.jason3.lon_lat > grid.outer。"""
    if override and len(override) >= 4:
        return [float(v) for v in override[:4]]
    cfg = config.plot.jason3
    if cfg.lon_lat and len(cfg.lon_lat) >= 4:
        return [float(v) for v in cfg.lon_lat[:4]]
    outer = config.grid.outer
    if outer.lon and outer.lat and len(outer.lon) >= 2 and len(outer.lat) >= 2:
        return [float(outer.lon[0]), float(outer.lon[1]), float(outer.lat[0]), float(outer.lat[1])]
    return None


def _resolve_jason3_time_range(
    config: PipelineConfig,
    override: Optional[List[str]] = None,
) -> Optional[List[str]]:
    """解析 Jason-3 时间范围：UI/CLI 覆盖 > plot.jason3.time_range > ww3 起止日期。"""
    if override and len(override) >= 2:
        return [str(override[0]), str(override[1])]
    cfg = config.plot.jason3
    if cfg.time_range and len(cfg.time_range) >= 2:
        return [str(cfg.time_range[0]), str(cfg.time_range[1])]
    if config.ww3.start_date and config.ww3.end_date:
        return [str(config.ww3.start_date), str(config.ww3.end_date)]
    return None


def _collect_png_images(result_folder: str, subdir: str) -> List[str]:
    """收集 ``photo/<subdir>`` 下的 PNG 文件。"""
    return collect_photo_files(result_folder, subdir, "*.png")


def _find_ww3_nc(result_folder: str) -> Optional[str]:
    """在结果目录中查找主 WW3 输出 nc 文件（排除谱文件）。"""
    candidates = glob.glob(os.path.join(result_folder, "ww3.*.nc"))
    candidates = [f for f in candidates if "spec" not in os.path.basename(f).lower()]
    if not candidates:
        candidates = glob.glob(os.path.join(result_folder, "ww3*.nc"))
        candidates = [f for f in candidates if "spec" not in os.path.basename(f).lower()]
    return candidates[0] if candidates else None


def run_match_jason3(
    config: PipelineConfig,
    log: Optional[LogCallback] = None,
    *,
    data_folder: Optional[str] = None,
) -> Jason3Result:
    """将 WW3 输出与 Jason-3 卫星 SWH 观测进行时空匹配并生成对比图。

    Args:
        config: 流水线配置，需设置 ``plot.jason3.data_folder``。
        log: 可选日志回调。

    Returns:
        ``Jason3Result``；配置缺失或未找到 WW3 nc 时 ``success=False``。
    """
    from ..infrastructure.plot.jason3_worker import _match_ww3_jason3_worker

    logger = CoreLogger(callback=log)
    result_folder = str(_resolve_result_folder(config))
    jason_folder = _resolve_jason3_data_folder(config, data_folder)
    if not jason_folder:
        return Jason3Result(
            output_folder=result_folder,
            messages=list(logger.messages),
            success=False,
            error=tr("plotting_jason3_data_folder_missing", "plot.jason3.data_folder 未配置"),
        )

    ww3_file = _find_ww3_nc(result_folder)
    if not ww3_file:
        return Jason3Result(
            output_folder=result_folder,
            messages=list(logger.messages),
            success=False,
            error=tr("plotting_ww3_output_nc_not_found", "未在 {folder} 找到 WW3 输出 nc 文件").format(folder=result_folder),
        )

    worker_result = run_plot_worker(
        _match_ww3_jason3_worker,
        (ww3_file, jason_folder, result_folder),
        kwargs={
            "max_dist_deg": config.plot.jason3.max_dist_deg,
            "time_window_hours": config.plot.jason3.time_window_hours,
        },
        on_log=logger.log,
    )

    images = _collect_png_images(result_folder, SUBDIR_JASON3_FIT)

    if worker_result and isinstance(worker_result, dict) and worker_result.get("status") == "error":
        return Jason3Result(
            output_folder=result_folder,
            image_files=images,
            messages=list(logger.messages),
            success=False,
            error=str(worker_result.get("error", tr("unknown_error", "未知错误"))),
        )

    logger.log(
        tr("plotting_jason3_match_generated", "Jason-3 匹配结果已生成至：{path}").format(
            path=photo_subdir(result_folder, SUBDIR_JASON3_FIT)
        )
    )
    return Jason3Result(
        output_folder=result_folder,
        image_files=images,
        messages=list(logger.messages),
    )


def run_jason3_swh(
    config: PipelineConfig,
    log: Optional[LogCallback] = None,
    *,
    lon_lat: Optional[List[float]] = None,
    time_range: Optional[List[str]] = None,
    data_folder: Optional[str] = None,
) -> Jason3Result:
    """绘制 Jason-3 SWH 沿轨或区域分布图（不与 WW3 对比）。

    Args:
        config: 流水线配置，需设置 ``plot.jason3.data_folder``。
        log: 可选日志回调。
        lon_lat: 可选，限定经纬度范围 ``[lon_min, lon_max, lat_min, lat_max]``。
        time_range: 可选，限定时间范围。

    Returns:
        ``Jason3Result``；配置缺失时 ``success=False``。
    """
    from ..infrastructure.plot.jason3_worker import _run_jason3_swh_worker

    logger = CoreLogger(callback=log)
    result_folder = str(_resolve_result_folder(config))

    jason_folder = _resolve_jason3_data_folder(config, data_folder)
    if not jason_folder:
        return Jason3Result(
            output_folder=result_folder,
            messages=list(logger.messages),
            success=False,
            error=tr("plotting_jason3_data_folder_missing", "plot.jason3.data_folder 未配置"),
        )

    effective_lon_lat = _resolve_jason3_lon_lat(config, lon_lat)
    if not effective_lon_lat:
        return Jason3Result(
            output_folder=result_folder,
            messages=list(logger.messages),
            success=False,
            error=tr("plotting_fill_lonlat_range", "请正确填写经纬度范围"),
        )

    effective_time_range = _resolve_jason3_time_range(config, time_range)
    if not effective_time_range:
        return Jason3Result(
            output_folder=result_folder,
            messages=list(logger.messages),
            success=False,
            error=tr("plotting_fill_time_range", "请填写开始和结束时间（格式：YYYYMMDD）"),
        )

    worker_result = run_plot_worker(
        _run_jason3_swh_worker,
        (effective_lon_lat, effective_time_range, jason_folder, result_folder),
        on_log=logger.log,
    )

    images = _collect_png_images(result_folder, SUBDIR_JASON3_SATELLITE)
    if not images and isinstance(worker_result, str) and os.path.isfile(worker_result):
        images = [worker_result]

    if worker_result and isinstance(worker_result, dict) and worker_result.get("status") == "error":
        return Jason3Result(
            output_folder=result_folder,
            image_files=images,
            messages=list(logger.messages),
            success=False,
            error=str(worker_result.get("error", tr("unknown_error", "未知错误"))),
        )

    logger.log(
        tr("plotting_jason3_swh_generated", "Jason-3 SWH 图已生成至：{path}").format(
            path=photo_subdir(result_folder, SUBDIR_JASON3_SATELLITE)
        )
    )
    return Jason3Result(
        output_folder=result_folder,
        image_files=images,
        messages=list(logger.messages),
    )
