"""桌面端外部边界谱后台检查与准备。"""

from __future__ import annotations

from typing import Callable, Optional

from workflows.application.boundary_preparation import (
    boundary_status,
    inspect_boundary,
    prepare_boundary_inputs,
)
from workflows.domain.config_models import PipelineConfig
from workflows.infrastructure.boundary.errors import BoundaryError
from workflows.support.translations import tr


LogCallback = Callable[[str], None]


class BoundaryViewModel:
    def __init__(self, *, on_log: Optional[LogCallback] = None) -> None:
        self._on_log = on_log
        self._cancel = False

    def request_cancel(self) -> None:
        self._cancel = True

    def _log(self, message: str) -> None:
        if self._on_log is not None:
            self._on_log(message)

    def inspect(self, config: PipelineConfig) -> dict:
        inspection = inspect_boundary(config, execution_context="local", depth="metadata", log=self._log)
        return {
            "success": inspection.state != "failed",
            "state": inspection.state,
            "pending_checks": list(inspection.pending_checks),
            "artifacts": dict(inspection.artifacts),
            "issues": [
                {"code": issue.code, "message": issue.message, "hints": list(issue.hints)}
                for issue in inspection.issues
            ],
        }

    def prepare(self, config: PipelineConfig) -> dict:
        self._cancel = False

        def cancel() -> None:
            if self._cancel:
                raise BoundaryError("BOUNDARY_WORKDIR_BUSY", tr("boundary_cancelled", "用户取消了边界准备"))

        result = prepare_boundary_inputs(config, execution_context="local", log=self._log, cancel=cancel)
        return {
            "success": result.ok,
            "state": result.state,
            "pending_checks": list(result.pending_checks),
            "artifacts": dict(result.outputs),
        }

    def status(self, config: PipelineConfig) -> dict:
        return boundary_status(config)
