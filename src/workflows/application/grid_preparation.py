"""Step 2 网格生成独立用例。

仅执行网格生成步骤，不导入强迫场或写入 WW3 namelist，
供桌面端「仅生成网格」按钮与 CLI 网格子命令调用。

流水线步骤：Step 2（网格生成）。

输入/输出
---------
- 输入：``PipelineConfig``（含 ``grid.*`` 与 ``workdir``）
- 输出：``GridGenerationResult``（工作目录路径与日志消息）

[EN] Step 2 grid generation standalone use case.

Only executes the grid generation step without importing forcing fields or writing
the WW3 namelist, for the desktop "generate grid only" button and CLI grid subcommands.

Pipeline step: Step 2 (grid generation).

Input/Output
------------
- Input: ``PipelineConfig`` (containing ``grid.*`` and ``workdir``)
- Output: ``GridGenerationResult`` (workdir path and log messages)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional

from ..domain.config_models import PipelineConfig
from ..infrastructure.adapters.grid_generation_adapter import (
    download_reference_data,
    generate_grid,
    list_missing_reference_data,
)
from ..support.logging import CoreLogger, LogCallback
from ..support.translations import tr
from .configuration import validate_pipeline_config


@dataclass
class GridGenerationResult:
    """网格生成步骤的执行结果。

    Attributes:
        workdir: 网格产物所在的工作目录绝对路径。
        messages: 执行过程中的日志消息列表。

    [EN] Execution result of the grid generation step.

    Attributes:
        workdir: Absolute path of the workdir containing grid artifacts.
        messages: Log message list during execution.
    """

    workdir: str
    messages: List[str] = field(default_factory=list)


def ensure_reference_data(
    config: PipelineConfig,
    log: Optional[LogCallback] = None,
    *,
    auto_download: bool = False,
    prompt_callback: Optional[Callable[[str, list[str]], bool]] = None,
) -> bool:
    """检查 reference_data 是否完整，必要时自动下载或交互式询问。

    参数:
        config: 流水线配置。
        log: 日志回调。
        auto_download: 缺失时是否直接下载（非交互式脚本使用）。
        prompt_callback: 交互式询问回调，接收 (ref_dir, missing) 返回 True/False。

    返回:
        True 表示 reference_data 已就绪；False 表示用户拒绝下载且数据缺失。

    [EN] Check whether reference_data is complete and download or prompt when missing.

    Args:
        config: Pipeline configuration.
        log: Optional log callback.
        auto_download: Download directly when files are missing (for non-interactive scripts).
        prompt_callback: Interactive prompt callback receiving (ref_dir, missing), returning True/False.

    Returns:
        True if reference_data is ready; False if the user declined and data is still missing.
    """
    _log = log or print
    ref_dir, missing = list_missing_reference_data(config.grid)
    if not missing:
        return True

    _log(
        tr(
            "ref_data_missing_prompt",
            "reference_data 目录中缺少必要的数据文件（海岸线、地形等），无法生成网格。\n\n路径：{path}\n\n是否从 GitHub 下载？（约 6.5 GB）",
        ).format(path=ref_dir)
    )

    if auto_download:
        _log(tr("ref_data_downloading", "📥 正在下载 reference_data（约 6.5 GB），请耐心等待..."))
        download_reference_data(config.grid, log=_log)
        return True

    if prompt_callback is not None:
        if prompt_callback(str(ref_dir), missing):
            _log(tr("ref_data_downloading", "📥 正在下载 reference_data（约 6.5 GB），请耐心等待..."))
            download_reference_data(config.grid, log=_log)
            return True
        return False

    return False


def run_generate_grid(
    config: PipelineConfig,
    log: Optional[LogCallback] = None,
    *,
    use_cache: bool = True,
) -> GridGenerationResult:
    """根据配置调用网格后端，生成网格相关产物。

    执行前以 ``stage="grid"`` 校验配置；会自动创建工作目录。

    Args:
        config: 流水线配置。
        log: 可选日志回调。

    Returns:
        含工作目录与完整日志的 ``GridGenerationResult``。

    [EN] Call the grid backend according to config to generate grid-related artifacts.
    Validates config with ``stage="grid"`` before execution; automatically creates the workdir.

    Args:
        config: Pipeline config.
        log: Optional log callback.

    Returns:
        ``GridGenerationResult`` with workdir and complete log.
    """
    validate_pipeline_config(config, stage="grid")
    logger = CoreLogger(callback=log)
    config.workdir.path.mkdir(parents=True, exist_ok=True)
    generate_grid(config, logger, use_cache=use_cache)
    logger.log(tr("status_grid_done", "✅ 网格生成完成"))
    return GridGenerationResult(
        workdir=str(config.workdir.path),
        messages=list(logger.messages),
    )
