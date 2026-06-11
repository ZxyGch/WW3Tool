"""Step 2 网格生成独立用例。

仅执行网格生成步骤，不导入强迫场或写入 WW3 namelist，
供桌面端「仅生成网格」按钮与 CLI 网格子命令调用。

流水线步骤：Step 2（网格生成）。

输入/输出
---------
- 输入：``PipelineConfig``（含 ``grid.*`` 与 ``workdir``）
- 输出：``GridGenerationResult``（工作目录路径与日志消息）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from ..domain.config_models import PipelineConfig
from ..infrastructure.adapters.grid_generation_adapter import generate_grid
from ..support.logging import CoreLogger, LogCallback
from ..support.translations import tr
from .configuration import validate_pipeline_config


@dataclass
class GridGenerationResult:
    """网格生成步骤的执行结果。

    Attributes:
        workdir: 网格产物所在的工作目录绝对路径。
        messages: 执行过程中的日志消息列表。
    """

    workdir: str
    messages: List[str] = field(default_factory=list)


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
    """
    validate_pipeline_config(config, stage="grid")
    logger = CoreLogger(callback=log)
    config.workdir.path.mkdir(parents=True, exist_ok=True)
    logger.log(tr("workdir_current", "工作目录：{folder}").format(folder=config.workdir.path))
    generate_grid(config, logger, use_cache=use_cache)
    logger.log(tr("status_grid_done", "网格生成完成"))
    return GridGenerationResult(
        workdir=str(config.workdir.path),
        messages=list(logger.messages),
    )
