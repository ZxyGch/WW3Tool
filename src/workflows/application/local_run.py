"""本地运行用例：Python 直驱 WW3 可执行文件（无需 bash）。

从 ``PipelineConfig`` 取工作目录、从 ST 版本配置或 ``config.json`` 取 bin 路径，调用
``LocalRunService.run_workflow()``。跨平台支持 Windows / macOS / Linux。

[EN] Local run use case: Python-native WW3 workflow driver (no bash needed).

Takes the workdir from ``PipelineConfig`` and bin path from ST version config or
``config.json``, calls ``LocalRunService.run_workflow()``. Cross-platform support
for Windows / macOS / Linux.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from ..domain.config_models import PipelineConfig
from ..infrastructure.local.run_service import LocalRunService
from ..support.logging import CoreLogger, LogCallback
from ..support.translations import tr


@dataclass
class LocalRunResult:
    success: bool = True
    messages: List[str] = field(default_factory=list)


def _bin_dir(config: Optional[PipelineConfig] = None, override: Optional[str] = None) -> str:
    if override:
        return str(override)
    if config is not None and config.paths.ww3bin_path:
        return str(config.paths.ww3bin_path)
    return ""


def run_local(
    config: PipelineConfig,
    service: LocalRunService,
    log: Optional[LogCallback] = None,
    *,
    bin_dir: Optional[str] = None,
) -> LocalRunResult:
    """Python 直驱 WW3 完整工作流（无需 bash / local.sh）。

    [EN] Run the full WW3 workflow in Python (no bash / local.sh needed).
    """
    logger = CoreLogger(callback=log)
    ret = service.run_workflow(str(config.workdir.path), _bin_dir(config, bin_dir), logger.log)
    return LocalRunResult(success=(ret == 0), messages=list(logger.messages))


def _run_tool(
    config: PipelineConfig, service: LocalRunService, tool: str, log: Optional[LogCallback], bin_dir: Optional[str]
) -> LocalRunResult:
    logger = CoreLogger(callback=log)
    ret = service.run_tool(tool, str(config.workdir.path), _bin_dir(config, bin_dir), logger.log)
    if ret == 0:
        logger.log(tr("step5_tool_completed", "✅ {tool} 已完成，输出文件已生成").format(tool=tool))
    elif ret not in (0, -1):
        logger.log(tr("step5_tool_failed", "❌ {tool} 失败（返回码 {code}）").format(tool=tool, code=ret))
    return LocalRunResult(success=(ret == 0), messages=list(logger.messages))


def run_ounf(config, service, log=None, *, bin_dir=None) -> LocalRunResult:
    return _run_tool(config, service, "ww3_ounf", log, bin_dir)


def run_ounp(config, service, log=None, *, bin_dir=None) -> LocalRunResult:
    return _run_tool(config, service, "ww3_ounp", log, bin_dir)


def run_trnc(config, service, log=None, *, bin_dir=None) -> LocalRunResult:
    return _run_tool(config, service, "ww3_trnc", log, bin_dir)
