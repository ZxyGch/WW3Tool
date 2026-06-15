"""Application use case for validating and merging NetCDF forcing files."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Sequence

from ..infrastructure.forcing.merge_service import MergeAnalysis, analyze_merge_inputs, merge_forcing_netcdf
from ..support.logging import CoreLogger, LogCallback
from ..support.translations import tr


ProgressCallback = Callable[[int, str], None]


@dataclass(frozen=True)
class ForcingMergeResult:
    """Result returned by the shared forcing merge application use case."""

    output_path: str
    analysis: MergeAnalysis
    messages: tuple[str, ...]


def run_merge_forcing(
    input_paths: Sequence[str],
    output_path: str,
    *,
    log: Optional[LogCallback] = None,
    progress: Optional[ProgressCallback] = None,
) -> ForcingMergeResult:
    """Validate and merge forcing files for CLI, shell, and other interfaces."""
    logger = CoreLogger(callback=log)
    analysis = analyze_merge_inputs(input_paths)
    if not analysis.valid:
        raise ValueError("\n".join(analysis.errors))

    logger.log(
        tr("merge_inline_valid", "校验通过：{strategy}，共 {steps} 个时间步").format(
            strategy=analysis.strategy,
            steps=analysis.time_steps,
        )
    )
    output = merge_forcing_netcdf(
        input_paths,
        output_path,
        log=logger,
        progress=progress,
    )
    return ForcingMergeResult(output, analysis, tuple(logger.messages))
