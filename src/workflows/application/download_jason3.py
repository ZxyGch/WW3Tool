"""Jason-3 卫星数据下载用例。

从 NCEI 远程目录按时间范围下载 Jason-3 L2 NetCDF 产品（GDR / IGDR / OGDR），
供 CLI ``download-jason3`` 命令与桌面后处理面板调用。

输入/输出
---------
- 输入：``PipelineConfig``（``plot.jason3.*`` 与结果目录）、时间范围、本地目录
- 输出：``Jason3DownloadResult``（下载目录、统计信息与成功标志）

[EN] Jason-3 satellite data download use case.

Downloads Jason-3 L2 NetCDF products (GDR / IGDR / OGDR) from NCEI remote directories
by time range, for the CLI ``download-jason3`` command and desktop post-processing panel.

Input/Output
------------
- Input: ``PipelineConfig`` (``plot.jason3.*`` and result directory), time range, local directory
- Output: ``Jason3DownloadResult`` (download directory, statistics and success flag)
"""

from __future__ import annotations

import os
from ..support.process_worker import run_plot_worker
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from ..domain.config_models import PipelineConfig
from ..support.logging import CoreLogger, LogCallback
from ..support.translations import tr


_DEFAULT_BASE_CATALOG_URL = "https://www.ncei.noaa.gov/data/oceans/jason3/"


@dataclass
class Jason3DownloadResult:
    """Jason-3 下载操作的返回结果。

    Attributes:
        output_folder: 数据下载目标目录。
        downloaded: 新增下载的文件数。
        skipped: 跳过（本地已存在）的文件数。
        failed: 下载失败的文件数。
        total: 远程候选文件总数。
        messages: 执行过程中的日志消息。
        success: 操作是否成功完成。
        error: 失败时的错误描述；成功时为 ``None``。

    [EN] Return result of Jason-3 download operation.

    Attributes:
        output_folder: Target directory for data download.
        downloaded: Number of newly downloaded files.
        skipped: Number of skipped files (already exist locally).
        failed: Number of failed downloads.
        total: Total number of remote candidate files.
        messages: Log messages during execution.
        success: Whether the operation completed successfully.
        error: Error description on failure; ``None`` on success.
    """

    output_folder: str
    downloaded: int = 0
    skipped: int = 0
    failed: int = 0
    total: int = 0
    messages: List[str] = field(default_factory=list)
    success: bool = True
    error: Optional[str] = None


def _resolve_result_folder(config: PipelineConfig) -> Path:
    """解析 WW3 结果目录：使用 ``workdir``。

    [EN] Resolve the WW3 result directory: use ``workdir``.
    """
    return config.workdir.path


def run_download_jason3(
    config: PipelineConfig,
    log: Optional[LogCallback] = None,
    *,
    time_range: Optional[List[str]] = None,
    local_folder: Optional[str] = None,
    base_catalog_url: str = _DEFAULT_BASE_CATALOG_URL,
) -> Jason3DownloadResult:
    """按时间范围从 NCEI 下载 Jason-3 L2 产品到本地目录。

    Args:
        config: 流水线配置；``plot.jason3.data_folder`` 为空时下载到 ``workdir/jason3_data``。
        log: 可选日志回调。
        time_range: ``[start_YYYYMMDD, end_YYYYMMDD]``；必填。
        local_folder: 可选，覆盖下载目标目录。
        base_catalog_url: NCEI Jason-3 产品根 URL。

    Returns:
        ``Jason3DownloadResult``；时间范围缺失时 ``success=False``。

    [EN] Download Jason-3 L2 products from NCEI to a local directory by time range.

    Args:
        config: Pipeline config; downloads to ``workdir/jason3_data`` when ``plot.jason3.data_folder`` is empty.
        log: Optional log callback.
        time_range: ``[start_YYYYMMDD, end_YYYYMMDD]``; required.
        local_folder: Optional, overrides the download target directory.
        base_catalog_url: NCEI Jason-3 product root URL.

    Returns:
        ``Jason3DownloadResult``; ``success=False`` when time range is missing.
    """
    from ..infrastructure.plot.jason3_download_worker import _download_jason3_worker

    from .match_jason3 import _resolve_jason3_data_folder, _resolve_jason3_time_range

    logger = CoreLogger(callback=log)
    result_folder = str(_resolve_result_folder(config))

    download_folder = (
        local_folder
        or _resolve_jason3_data_folder(config)
        or os.path.join(result_folder, "jason3_data")
    )
    os.makedirs(download_folder, exist_ok=True)

    effective_time_range = _resolve_jason3_time_range(config, time_range)
    if not effective_time_range:
        return Jason3DownloadResult(
            output_folder=download_folder,
            messages=list(logger.messages),
            success=False,
            error=tr(
                "plotting_jason_download_time_range_missing",
                "❌ time_range 必须提供 [起始日期, 结束日期]（格式 YYYYMMDD）",
            ),
        )

    worker_result = run_plot_worker(
        _download_jason3_worker,
        (effective_time_range, download_folder, base_catalog_url),
        on_log=logger.log,
    )

    if worker_result and isinstance(worker_result, dict):
        if not worker_result.get("ok", False):
            return Jason3DownloadResult(
                output_folder=download_folder,
                downloaded=worker_result.get("downloaded", 0),
                skipped=worker_result.get("skipped", 0),
                failed=worker_result.get("failed", 0),
                total=worker_result.get("total", 0),
                messages=list(logger.messages),
                success=False,
                error=tr("plotting_jason_download_not_ok", "⚠️ 下载未完全成功"),
            )

        logger.log(
            tr(
                "plotting_jason_download_finished",
                "✅ Jason-3 数据已下载至：{path}",
            ).format(path=download_folder)
        )
        return Jason3DownloadResult(
            output_folder=download_folder,
            downloaded=worker_result.get("downloaded", 0),
            skipped=worker_result.get("skipped", 0),
            failed=worker_result.get("failed", 0),
            total=worker_result.get("total", 0),
            messages=list(logger.messages),
        )

    # worker 没有返回结果字典
    # [EN] Worker did not return a result dictionary.
    return Jason3DownloadResult(
        output_folder=download_folder,
        messages=list(logger.messages),
        success=False,
        error=tr("unknown_error", "❌ 未知错误"),
    )
