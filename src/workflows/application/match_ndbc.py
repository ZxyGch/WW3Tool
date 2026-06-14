"""NDBC 浮标观测匹配与数据下载用例。

将 WW3 模式输出与 NDBC 浮标观测进行比对，或按区域与时间范围下载 NDBC 数据，
供 CLI ``plot-ndbc`` 命令与桌面后处理面板调用。

流水线步骤：后处理（Step 4 结果验证）— 浮标观测对比。

输入/输出
---------
- 输入：``PipelineConfig``（``plot.ndbc.*`` 与结果目录）
- 输出：``NDBCResult``（输出目录、PNG 列表、成功标志与错误信息）
"""

from __future__ import annotations

import glob
import os
from ..support.process_worker import run_plot_worker
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from ..domain.config_models import PipelineConfig
from ..infrastructure.plot.photo_output import SUBDIR_NDBC_FIT, collect_photo_files, photo_subdir
from ..support.logging import CoreLogger, LogCallback
from ..support.translations import tr


@dataclass
class NDBCResult:
    """NDBC 匹配或下载操作的返回结果。

    Attributes:
        output_folder: 结果或数据输出目录。
        image_files: 生成的 PNG 图片路径列表（下载操作可能为空）。
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
    """解析 WW3 结果目录：使用 ``workdir``。"""
    return config.workdir.path


def load_ndbc_station_points(
    lon_lat: List[float],
    time_range: List[str],
    local_folder: str = "",
) -> List[dict]:
    """加载指定经纬度范围内的 NDBC 浮标站点（本地元数据或 NOAA 活跃站点 API）。"""
    from ..infrastructure.plot.ndbc_worker import _load_ndbc_stations_from_folder

    return _load_ndbc_stations_from_folder(local_folder or "", lon_lat, time_range)


def _find_ww3_nc(result_folder: str) -> Optional[str]:
    """在结果目录中查找主 WW3 输出 nc 文件（排除谱文件）。"""
    candidates = glob.glob(os.path.join(result_folder, "ww3.*.nc"))
    candidates = [f for f in candidates if "spec" not in os.path.basename(f).lower()]
    if not candidates:
        candidates = glob.glob(os.path.join(result_folder, "ww3*.nc"))
        candidates = [f for f in candidates if "spec" not in os.path.basename(f).lower()]
    return candidates[0] if candidates else None


def run_match_ndbc(
    config: PipelineConfig,
    log: Optional[LogCallback] = None,
    *,
    lon_lat: Optional[List[float]] = None,
    time_range: Optional[List[str]] = None,
) -> NDBCResult:
    """将 WW3 输出与 NDBC 浮标观测进行时空匹配并生成对比图。

    Args:
        config: 流水线配置，需设置 ``plot.ndbc.data_folder``。
        log: 可选日志回调。
        lon_lat: 可选，限定匹配区域 ``[lon_min, lon_max, lat_min, lat_max]``。
        time_range: 可选，覆盖配置中的 ``plot.ndbc.time_range``。

    Returns:
        ``NDBCResult``；配置缺失或未找到 WW3 nc 时 ``success=False``。
    """
    from ..infrastructure.plot.ndbc_worker import _match_ww3_ndbc_worker

    logger = CoreLogger(callback=log)
    result_folder = str(_resolve_result_folder(config))
    cfg = config.plot.ndbc

    if not cfg.data_folder:
        return NDBCResult(
            output_folder=result_folder,
            messages=list(logger.messages),
            success=False,
            error=tr("plotting_ndbc_data_folder_missing", "❌ plot.ndbc.data_folder 未配置"),
        )

    ww3_file = _find_ww3_nc(result_folder)
    if not ww3_file:
        return NDBCResult(
            output_folder=result_folder,
            messages=list(logger.messages),
            success=False,
            error=tr("plotting_ww3_output_nc_not_found", "❌ 未在 {folder} 找到 WW3 输出 nc 文件").format(folder=result_folder),
        )

    out_folder = os.path.join(result_folder, "ndbc_match")
    os.makedirs(out_folder, exist_ok=True)

    effective_lon_lat = lon_lat or []
    effective_time_range = time_range or cfg.time_range

    worker_result = run_plot_worker(
        _match_ww3_ndbc_worker,
        (
            ww3_file,
            str(cfg.data_folder),
            out_folder,
            effective_lon_lat,
            effective_time_range,
        ),
        on_log=logger.log,
    )

    images = collect_photo_files(result_folder, SUBDIR_NDBC_FIT, "*.png")

    if worker_result and isinstance(worker_result, dict) and worker_result.get("status") == "error":
        return NDBCResult(
            output_folder=result_folder,
            image_files=images,
            messages=list(logger.messages),
            success=False,
            error=str(worker_result.get("error", tr("unknown_error", "❌ 未知错误"))),
        )

    logger.log(
        tr("plotting_ndbc_match_generated", "✅ NDBC 匹配结果已生成至：{path}").format(
            path=photo_subdir(result_folder, SUBDIR_NDBC_FIT)
        )
    )
    return NDBCResult(
        output_folder=result_folder,
        image_files=images,
        messages=list(logger.messages),
    )


def run_download_ndbc(
    config: PipelineConfig,
    log: Optional[LogCallback] = None,
    *,
    lon_lat: Optional[List[float]] = None,
    time_range: Optional[List[str]] = None,
) -> NDBCResult:
    """按区域与时间范围从 NDBC 下载浮标观测数据。

    Args:
        config: 流水线配置；``plot.ndbc.data_folder`` 为空时下载至 ``workdir/ndbc_data``。
        log: 可选日志回调。
        lon_lat: 可选，限定下载区域。
        time_range: 可选，覆盖配置中的 ``plot.ndbc.time_range``；须含起止日期。

    Returns:
        ``NDBCResult``；时间范围不完整时 ``success=False``。
    """
    from ..infrastructure.plot.ndbc_worker import _download_ndbc_worker

    logger = CoreLogger(callback=log)
    result_folder = str(_resolve_result_folder(config))
    cfg = config.plot.ndbc

    download_folder = str(cfg.data_folder) if cfg.data_folder else os.path.join(result_folder, "ndbc_data")
    os.makedirs(download_folder, exist_ok=True)

    effective_lon_lat = lon_lat or []
    effective_time_range = time_range or cfg.time_range
    if len(effective_time_range) < 2:
        return NDBCResult(
            output_folder=download_folder,
            messages=list(logger.messages),
            success=False,
            error="plot.ndbc.time_range 必须提供 [起始日期, 结束日期]",
        )

    worker_result = run_plot_worker(
        _download_ndbc_worker,
        (effective_lon_lat, effective_time_range, download_folder),
        on_log=logger.log,
    )

    if worker_result and isinstance(worker_result, dict) and worker_result.get("status") == "error":
        return NDBCResult(
            output_folder=download_folder,
            messages=list(logger.messages),
            success=False,
            error=str(worker_result.get("error", tr("unknown_error", "❌ 未知错误"))),
        )

    logger.log(tr("plotting_ndbc_downloaded_to", "✅ NDBC 数据已下载至：{path}").format(path=download_folder))
    return NDBCResult(
        output_folder=download_folder,
        messages=list(logger.messages),
    )
