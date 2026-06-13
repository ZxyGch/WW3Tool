"""本地运行视图模型：桥接桌面到 application.local_run，并持有可停止的执行服务。

[EN] Local run view model: bridges desktop to application.local_run and holds a stoppable execution service.
"""

from __future__ import annotations

from typing import Callable, Optional

from workflows.domain.config_models import PipelineConfig
from workflows.infrastructure.local.run_service import LocalRunService

LogCallback = Callable[[str], None]


class LocalRunViewModel:
    # [EN] Drive local WW3 runs and ww3_ounf/ounp/trnc, with stop support.
    """驱动本地 WW3 运行与 ww3_ounf/ounp/trnc，支持停止。"""

    def __init__(self, *, on_log: Optional[LogCallback] = None) -> None:
        self._on_log = on_log
        self._service = LocalRunService()

    def _log(self, message: str) -> None:
        if self._on_log is not None:
            self._on_log(str(message))

    def local_run(self, config: PipelineConfig, *, bin_dir: Optional[str] = None):
        from workflows.application.local_run import run_local

        return run_local(config, self._service, log=self._log, bin_dir=bin_dir)

    def ounf(self, config: PipelineConfig, *, bin_dir: Optional[str] = None):
        from workflows.application.local_run import run_ounf

        return run_ounf(config, self._service, log=self._log, bin_dir=bin_dir)

    def ounp(self, config: PipelineConfig, *, bin_dir: Optional[str] = None):
        from workflows.application.local_run import run_ounp

        return run_ounp(config, self._service, log=self._log, bin_dir=bin_dir)

    def trnc(self, config: PipelineConfig, *, bin_dir: Optional[str] = None):
        from workflows.application.local_run import run_trnc

        return run_trnc(config, self._service, log=self._log, bin_dir=bin_dir)

    def stop(self) -> bool:
        return self._service.stop()
