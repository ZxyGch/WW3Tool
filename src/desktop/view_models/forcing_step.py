"""Desktop adapter for Step 2 forcing preparation.

This module is intentionally toolkit agnostic. A desktop page can call this
view model directly and bind ``on_log`` / ``on_state_change`` to signals or
slots. Command entrypoints use the same ``workflows`` functions, so desktop
and automated execution stay aligned.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, List, Optional

from workflows.application.configuration import load_pipeline_config, parse_pipeline_config
from workflows.domain.config_models import PipelineConfig
from workflows.domain.forcing_fields import ForcingField, Step2Files
from workflows.support.translations import tr


LogCallback = Callable[[str], None]
StateCallback = Callable[["ForcingStepState"], None]


@dataclass
class ForcingStepState:
    is_running: bool = False
    workdir: str = ""
    files: Step2Files = field(default_factory=Step2Files)
    messages: List[str] = field(default_factory=list)
    error: Optional[str] = None


class ForcingStepViewModel:
    """Small bridge from a future UI page to the headless forcing core."""

    def __init__(
        self,
        *,
        on_log: Optional[LogCallback] = None,
        on_state_change: Optional[StateCallback] = None,
    ) -> None:
        self._on_log = on_log
        self._on_state_change = on_state_change
        self.state = ForcingStepState()

    def load_config(self, params_path: str | Path) -> PipelineConfig:
        return load_pipeline_config(params_path, validation_stage="forcing")

    def config_from_selection(
        self,
        *,
        workdir: str | Path,
        wind: str | Path,
        current: str | Path | None = None,
        level: str | Path | None = None,
        ice: str | Path | None = None,
        process_mode: str = "copy",
        auto_associate: bool = True,
        crop_time_range: list[str] | None = None,
        crop_bbox: list[float] | None = None,
        custom: dict | None = None,
    ) -> PipelineConfig:
        return parse_pipeline_config(
            {
                "workdir": {"path": str(workdir)},
                "forcing": {
                    "wind": str(wind),
                    "current": str(current) if current else None,
                    "level": str(level) if level else None,
                    "ice": str(ice) if ice else None,
                    "process_mode": process_mode,
                    "auto_associate": auto_associate,
                    "crop_time_range": crop_time_range or [],
                    "crop_bbox": crop_bbox or [],
                    "custom": custom or {},
                },
            },
            base_dir=Path.cwd(),
            validation_stage="forcing",
        )

    def prepare_from_file(self, params_path: str | Path) -> ForcingStepState:
        return self.prepare(self.load_config(params_path))

    def report_file_overviews(self, files: Step2Files) -> list[str]:
        from workflows.application.forcing_inspection import report_forcing_file_overviews

        return report_forcing_file_overviews(files, log=self._handle_log)

    def prepare(
        self,
        config: PipelineConfig,
        *,
        fields: Iterable[ForcingField] | None = None,
    ) -> ForcingStepState:
        self._set_state(
            ForcingStepState(
                is_running=True,
                workdir=str(config.workdir.path),
                messages=list(self.state.messages),
            )
        )
        try:
            from workflows.application.preprocessing_workflow import run_prepare_forcing

            result = run_prepare_forcing(config, log=self._handle_log, fields=fields)
            self._set_state(
                ForcingStepState(
                    is_running=False,
                    workdir=result.workdir,
                    files=result.forcing_files,
                    messages=result.messages,
                )
            )
        except Exception as exc:
            self._handle_log(tr("step2_prepare_failed", "❌ 强迫场准备失败：{error}").format(error=exc))
            self._set_state(
                ForcingStepState(
                    is_running=False,
                    workdir=str(config.workdir.path),
                    files=self.state.files,
                    messages=list(self.state.messages),
                    error=str(exc),
                )
            )
        return self.state

    def _handle_log(self, message: str) -> None:
        text = str(message)
        self.state.messages.append(text)
        if self._on_log is not None:
            self._on_log(text)

    def _set_state(self, state: ForcingStepState) -> None:
        self.state = state
        if self._on_state_change is not None:
            self._on_state_change(state)
