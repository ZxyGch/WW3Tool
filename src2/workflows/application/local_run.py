"""本地运行用例：执行 local.sh 与 ww3_ounf/ounp/trnc。

从 ``PipelineConfig`` 取工作目录、从 ``config.json`` 取 ``WW3BIN_PATH``，调用
``LocalRunService``。``local.sh`` 缺失时回退仓库 ``public/ww3/local.sh``。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from ..domain.config_models import PipelineConfig
from ..infrastructure import runtime_config
from ..infrastructure.local.run_service import LocalRunService
from ..support.logging import CoreLogger, LogCallback
from ..support.translations import tr


@dataclass
class LocalRunResult:
    success: bool = True
    messages: List[str] = field(default_factory=list)


def _bin_dir(override: Optional[str] = None) -> str:
    if override:
        return str(override)
    try:
        return str(runtime_config.load_config().get("WW3BIN_PATH", "") or "")
    except Exception:
        return ""


def _fallback_script() -> str:
    return str(Path(runtime_config.get_project_root()) / "public" / "ww3" / "local.sh")


def run_local(
    config: PipelineConfig,
    service: LocalRunService,
    log: Optional[LogCallback] = None,
    *,
    bin_dir: Optional[str] = None,
) -> LocalRunResult:
    """运行工作目录下的 ``local.sh``（流式日志，可经 ``service.stop()`` 停止）。"""
    logger = CoreLogger(callback=log)
    ret = service.run_script(str(config.workdir.path), _bin_dir(bin_dir), logger.log, fallback_script=_fallback_script())
    if ret == 0:
        logger.log(tr("step5_local_run_completed", "✅ 本地 WW3 运行已完成"))
    elif ret not in (0, -1):
        logger.log(tr("step5_local_run_failed", "❌ 本地 WW3 运行失败（返回码 {code}）").format(code=ret))
    return LocalRunResult(success=(ret == 0), messages=list(logger.messages))


def _run_tool(
    config: PipelineConfig, service: LocalRunService, tool: str, log: Optional[LogCallback], bin_dir: Optional[str]
) -> LocalRunResult:
    logger = CoreLogger(callback=log)
    ret = service.run_tool(tool, str(config.workdir.path), _bin_dir(bin_dir), logger.log)
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
