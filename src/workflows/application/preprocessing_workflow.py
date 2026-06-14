"""无界面预处理流水线编排用例。

串联 Step 1 强迫场准备、Step 2 网格生成与 WW3 namelist 写入，
实现完整的本地预处理流程（不含远程提交与后处理绘图）。

流水线步骤：Step 1 + Step 2 + WW3 文件准备（完整预处理）。

输入/输出
---------
- 输入：``PipelineConfig``
- 输出：``PipelineResult``（工作目录、强迫场文件映射、日志消息）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List, Optional

from ..domain.config_models import PipelineConfig
from ..domain.forcing_fields import ForcingField, Step1Files
from ..infrastructure.adapters.grid_generation_adapter import generate_grid
from ..infrastructure.adapters.ww3_namelist_adapter import prepare_ww3_files
from ..support.logging import CoreLogger, LogCallback
from ..support.translations import tr
from .configuration import validate_pipeline_config
from .forcing_preparation import prepare_forcing


@dataclass
class PipelineResult:
    """预处理流水线（或单步强迫场准备）的执行结果。

    Attributes:
        workdir: 工作目录绝对路径。
        forcing_files: 各强迫场类型在工作目录中的文件路径。
        messages: 执行过程中的日志消息列表。
    """

    workdir: str
    forcing_files: Step1Files
    messages: List[str] = field(default_factory=list)


def run_pipeline(
    config: PipelineConfig,
    log: Optional[LogCallback] = None,
    *,
    skip_grid: bool = False,
    use_grid_cache: bool = True,
) -> PipelineResult:
    """运行完整无界面预处理：强迫场 → 网格 → WW3 namelist。

    Args:
        config: 流水线配置。
        log: 可选日志回调。
        skip_grid: 为 ``True`` 时跳过网格生成，复用工作目录中已有网格文件。
        use_grid_cache: 为 ``False`` 时强制重新生成网格，不读取或写入网格缓存。

    Returns:
        含工作目录、强迫场路径与日志的 ``PipelineResult``。
    """
    validate_pipeline_config(config, stage="full")
    logger = CoreLogger(callback=log)
    config.workdir.path.mkdir(parents=True, exist_ok=True)

    logger.log(tr("workdir_current", "工作目录：{folder}").format(folder=config.workdir.path))
    files = prepare_forcing(config, logger)
    if skip_grid:
        logger.log(tr("pipeline_skip_grid", "已跳过网格生成，将使用工作目录中已有网格文件"))
    else:
        generate_grid(config, logger, use_cache=use_grid_cache)
    prepare_ww3_files(config, files, logger)
    logger.log(tr("pipeline_headless_done", "无 UI 预处理完成"))

    return PipelineResult(
        workdir=str(config.workdir.path),
        forcing_files=files,
        messages=list(logger.messages),
    )


def run_prepare_forcing(
    config: PipelineConfig,
    log: Optional[LogCallback] = None,
    *,
    fields: Iterable[ForcingField] | None = None,
) -> PipelineResult:
    """仅执行 Step 1 强迫场准备，供 CLI 与未来 UI 增量更新调用。

    Args:
        config: 流水线配置。
        log: 可选日志回调。
        fields: 可选，限定本次处理的场类型；``None`` 表示全部已配置场。

    Returns:
        含工作目录、强迫场路径与日志的 ``PipelineResult``。
    """
    validate_pipeline_config(config, stage="forcing")
    logger = CoreLogger(callback=log)
    config.workdir.path.mkdir(parents=True, exist_ok=True)
    files = prepare_forcing(config, logger, fields=fields)
    return PipelineResult(
        workdir=str(config.workdir.path),
        forcing_files=files,
        messages=list(logger.messages),
    )
