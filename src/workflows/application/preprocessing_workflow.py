"""无界面预处理流水线编排用例。

串联 Step 1 网格生成、Step 2 强迫场准备与 WW3 namelist 写入，
实现完整的本地预处理流程（不含远程提交与后处理绘图）。

流水线步骤：Step 1 + Step 2 + WW3 文件准备（完整预处理）。

输入/输出
---------
- 输入：``PipelineConfig``
- 输出：``PipelineResult``（工作目录、强迫场文件映射、日志消息）

[EN] Headless preprocessing pipeline orchestration use case.

Chains Step 1 grid generation, Step 2 forcing field preparation, and WW3 namelist writing,
implementing the complete local preprocessing workflow (without remote submission and post-processing plots).

Pipeline step: Step 1 + Step 2 + WW3 file preparation (full preprocessing).

Input/Output
------------
- Input: ``PipelineConfig``
- Output: ``PipelineResult`` (workdir, forcing file mapping, log messages)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List, Optional

from ..domain.config_models import PipelineConfig
from ..domain.forcing_fields import ForcingField, Step2Files
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

    [EN] Execution result of the preprocessing pipeline (or single-step forcing preparation).

    Attributes:
        workdir: Absolute path of the working directory.
        forcing_files: File paths for each forcing field type in the workdir.
        messages: List of log messages during execution.
    """

    workdir: str
    forcing_files: Step2Files
    messages: List[str] = field(default_factory=list)


def run_pipeline(
    config: PipelineConfig,
    log: Optional[LogCallback] = None,
    *,
    skip_grid: bool = False,
    use_grid_cache: bool = True,
) -> PipelineResult:
    """运行完整无界面预处理：网格 → 强迫场 → WW3 namelist。

    Args:
        config: 流水线配置。
        log: 可选日志回调。
        skip_grid: 为 ``True`` 时跳过网格生成，复用工作目录中已有网格文件。
        use_grid_cache: 为 ``False`` 时强制重新生成网格，不读取或写入网格缓存。

    Returns:
        含工作目录、强迫场路径与日志的 ``PipelineResult``。

    [EN] Run the complete headless preprocessing: grid → forcing → WW3 namelist.

    Args:
        config: Pipeline config.
        log: Optional log callback.
        skip_grid: When ``True``, skip grid generation and reuse existing grid files in the workdir.
        use_grid_cache: When ``False``, force grid regeneration without reading or writing grid cache.

    Returns:
        ``PipelineResult`` containing workdir, forcing file paths, and logs.
    """
    validate_pipeline_config(config, stage="full")
    logger = CoreLogger(callback=log)
    config.workdir.path.mkdir(parents=True, exist_ok=True)

    logger.log(tr("workdir_current", "📂 工作目录：{folder}").format(folder=config.workdir.path))
    if skip_grid:
        logger.log(tr("pipeline_skip_grid", "ℹ️ 已跳过网格生成，将使用工作目录中已有网格文件"))
    else:
        generate_grid(config, logger, use_cache=use_grid_cache)
    files = prepare_forcing(config, logger)
    prepare_ww3_files(config, files, logger)
    logger.log(tr("pipeline_headless_done", "✅ 无 UI 预处理完成"))

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
    """仅执行 Step 2 强迫场准备，供 CLI 与未来 UI 增量更新调用。

    Args:
        config: 流水线配置。
        log: 可选日志回调。
        fields: 可选，限定本次处理的场类型；``None`` 表示全部已配置场。

    Returns:
        含工作目录、强迫场路径与日志的 ``PipelineResult``。

    [EN] Execute Step 2 forcing field preparation only, for CLI and future UI incremental updates.

    Args:
        config: Pipeline config.
        log: Optional log callback.
        fields: Optional, restricts the field types to process; ``None`` means all configured fields.

    Returns:
        ``PipelineResult`` containing workdir, forcing file paths, and logs.
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
