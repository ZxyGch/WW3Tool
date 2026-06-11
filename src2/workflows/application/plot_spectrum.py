"""WW3 二维方向谱绘图用例。

从工作目录或指定结果文件夹中的谱输出 NetCDF 生成二维频谱图，
供 CLI ``plot-spectrum`` 命令与桌面后处理面板调用。

流水线步骤：后处理（Step 4 结果可视化）— 方向谱。

输入/输出
---------
- 输入：``PipelineConfig``（``plot.spectrum.*`` 与结果目录）
- 输出：``SpectrumResult``（输出目录、PNG 列表、成功标志与错误信息）
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
    SUBDIR_DIRECTIONAL_SPECTRUM,
    collect_photo_files,
    photo_subdir,
)
from ..support.logging import CoreLogger, LogCallback
from ..support.translations import tr


@dataclass
class SpectrumResult:
    """方向谱绘图操作的返回结果。

    Attributes:
        output_folder: WW3 结果根目录（图片位于其下 ``photo/`` 子目录）。
        image_files: 生成的 ``spectrum_*.png`` 路径列表。
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


def run_spectrum(
    config: PipelineConfig,
    log: Optional[LogCallback] = None,
    *,
    mode: str = "all",
    station_index: int = 0,
    spec_file: Optional[str] = None,
) -> SpectrumResult:
    """从 WW3 谱输出 NetCDF 生成二维方向谱图。

    Args:
        config: 流水线配置（``plot.spectrum`` 段控制阈值与绘图模式）。
        log: 可选日志回调。
        mode: 绘图范围 — ``"first"`` 仅首站/首时次，``"all"`` 全部，
            ``"selected"`` 按 ``station_index`` 选取单站。
        station_index: ``mode="selected"`` 时使用的站点索引。
        spec_file: 可选，指定谱 nc 文件路径；省略时自动搜索。

    Returns:
        ``SpectrumResult``；worker 报错时 ``success=False``。
    """
    from ..infrastructure.plot.spectrum_worker import (
        _generate_all_spectrum_worker,
        _generate_first_spectrum_worker,
        _generate_selected_spectrum_worker,
    )

    logger = CoreLogger(callback=log)
    result_folder = _resolve_result_folder(config)
    cfg = config.plot.spectrum

    folder_str = str(result_folder)

    if mode == "first":
        worker = _generate_first_spectrum_worker
        worker_kwargs = {
            "energy_threshold": cfg.energy_threshold,
            "spec_file": spec_file,
        }
    elif mode == "selected":
        worker = _generate_selected_spectrum_worker
        worker_kwargs = {
            "energy_threshold": cfg.energy_threshold,
            "spec_file": spec_file,
            "time_step_hours": cfg.time_step_hours,
            "station_index": station_index,
            "plot_mode": cfg.plot_mode,
        }
    else:
        worker = _generate_all_spectrum_worker
        worker_kwargs = {
            "energy_threshold": cfg.energy_threshold,
            "spec_file": spec_file,
            "time_step_hours": cfg.time_step_hours,
            "plot_mode": cfg.plot_mode,
        }

    worker_result = run_plot_worker(
        worker,
        (folder_str,),
        kwargs=worker_kwargs,
        on_log=logger.log,
    )

    photo_dir = photo_subdir(folder_str, SUBDIR_DIRECTIONAL_SPECTRUM)
    images = collect_photo_files(folder_str, SUBDIR_DIRECTIONAL_SPECTRUM, "spectrum_*.png")

    if worker_result and isinstance(worker_result, dict) and worker_result.get("status") == "error":
        return SpectrumResult(
            output_folder=folder_str,
            image_files=images,
            messages=list(logger.messages),
            success=False,
            error=str(worker_result.get("error", tr("unknown_error", "未知错误"))),
        )

    logger.log(tr("plotting_spectrum_generated_to", "频谱图已生成至：{path}").format(path=photo_dir))
    return SpectrumResult(
        output_folder=folder_str,
        image_files=images,
        messages=list(logger.messages),
    )
