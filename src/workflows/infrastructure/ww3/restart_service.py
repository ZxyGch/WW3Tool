"""Restart / hot-start file preparation helpers.

This module prepares user-specified restart files before upload or local run.
Auto Latest is intentionally handled by ``local.sh`` / ``server.sh`` at runtime,
because the latest checkpoint may be produced on the server after WW3Tool is no
longer running.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from ...domain.config_models import PipelineConfig
from ...support.logging import CoreLogger
from ...support.translations import tr


def prepare_manual_restart_inputs(config: PipelineConfig, logger: CoreLogger) -> None:
    """Copy manually selected restart files into the workdir.

    ``pick_latest_checkpoint=true`` does not copy anything here; runtime scripts
    select timestamped checkpoints directly in the workdir.
    """

    restart = config.restart
    if restart.mode != "restart" or restart.pick_latest_checkpoint:
        return

    input_file = restart.input_file
    if not input_file:
        logger.log(
            tr(
                "restart_manual_existing_input",
                "ℹ️ 手动热启动未指定 Restart 文件，将使用工作目录中已有的 restart 输入",
            )
        )
        return

    workdir = config.workdir.path
    if config.grid.grid_type == "nested":
        _copy_nested_restart_inputs(input_file, workdir, logger)
    else:
        _copy_single_restart_input(input_file, workdir / "restart.ww3", logger)


def _copy_single_restart_input(input_file: Any, destination: Path, logger: CoreLogger) -> None:
    if isinstance(input_file, (dict, list, tuple)):
        raise ValueError("普通网格的 ww3.restart.input_file 必须是单个文件路径")
    src = Path(str(input_file)).expanduser()
    if not src.is_file():
        raise FileNotFoundError(f"Restart 文件不存在：{src}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if src.resolve() != destination.resolve():
        shutil.copyfile(src, destination)
    logger.log(
        tr("restart_file_prepared", "✅ 已准备 Restart 文件：{src} → {dst}").format(
            src=src,
            dst=destination,
        )
    )


def _copy_nested_restart_inputs(input_file: Any, workdir: Path, logger: CoreLogger) -> None:
    mapping = _normalise_nested_mapping(input_file)
    if not mapping:
        raise ValueError("嵌套网格的 ww3.restart.input_file 必须是 {level0: path, level1: path, ...}")
    for level_name, src_raw in mapping.items():
        level = str(level_name).strip()
        if not level:
            continue
        destination = workdir / level / "restart.ww3"
        _copy_single_restart_input(src_raw, destination, logger)


def _normalise_nested_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return {str(k): v for k, v in value.items()}
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("{"):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                return {}
            if isinstance(parsed, dict):
                return {str(k): v for k, v in parsed.items()}
    return {}
