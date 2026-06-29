"""Slurm idle-resource query and server.sh confirmation (shared by GUI, shell, CLI)."""

from __future__ import annotations

from typing import Optional

from ..domain.config_models import PipelineConfig
from ..infrastructure.adapters.ww3_namelist_adapter import update_server_script
from ..support.logging import CoreLogger, LogCallback
from .remote_ops import RemoteResult, run_slurm_idle_resources


def run_slurm_idle(config: PipelineConfig, log: Optional[LogCallback] = None) -> RemoteResult:
    """Query and print Slurm idle CPU resources."""
    return run_slurm_idle_resources(config, log=log)


def run_confirm_slurm(
    config: PipelineConfig,
    params_path: str,
    log: Optional[LogCallback] = None,
) -> int:
    """Apply Slurm settings from params.yml and regenerate ``server.sh``."""
    logger = CoreLogger(callback=log)
    update_server_script(config, logger)
    return 0
