"""在子进程中运行网格可视化 worker。

设计说明 — 为何使用子进程而非进程内调用
----------------------------------------
``grid_visualization/worker.py`` 使用 matplotlib ``Agg`` 后端并将 PNG 写入磁盘。
桌面端在 Qt 事件循环中若于同一进程导入 matplotlib 并切换后端，易与 Qt 冲突导致崩溃。
子进程为 matplotlib 提供干净、隔离的运行环境。

对比：``infrastructure/plot/`` 下的 worker 在特定场景下进程内调用，因主窗口未同时
展示 Qt 画布时后端冲突概率较低。若未来统一问题复现，可一并改为子进程模式。

[EN] Run the grid visualization worker in a subprocess.

Design rationale — why a subprocess instead of an in-process call
------------------------------------------------------------------
``grid_visualization/worker.py`` uses the matplotlib ``Agg`` backend and writes
PNG files to disk. Importing matplotlib and switching backends within the same
process while the Qt event loop is active easily causes crashes due to Qt
conflicts. A subprocess provides a clean, isolated environment for matplotlib.

By contrast, workers under ``infrastructure/plot/`` are called in-process in
certain scenarios, since the main window does not simultaneously display a Qt
canvas and backend conflict probability is lower. If the same issue resurfaces
in the future, those can be migrated to subprocess mode as well.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from ...domain.config_models import GridRegion, PipelineConfig
from ...support.logging import CoreLogger


_RESULT_PREFIX = "WW3TOOL_VIZ\tRESULT\t"
_LOG_PREFIX = "WW3TOOL_VIZ\tLOG\t"


def generate_grid_images(config: PipelineConfig, logger: CoreLogger) -> list[str]:
    """为当前流水线配置生成网格预览 PNG 路径列表。

    嵌套网格分别对各 ``level*`` 子目录调用 worker；普通网格按
    ``mesh_type`` 选择 structured/smc/unst 模式。

    参数:
        config: 流水线配置（含工作目录与网格类型）
        logger: 接收 worker 标准输出中的日志行

    返回:
        已生成 PNG 文件的绝对路径列表

    异常:
        RuntimeError: worker 失败或未产生任何图片

    [EN] Generate a list of grid preview PNG paths for the current pipeline configuration.

    For nested grids, the worker is invoked separately for each ``level*`` subdirectory;
    for regular grids, the structured/smc/unst mode is selected by ``mesh_type``.

    Args:
        config: Pipeline configuration (containing working directory and grid type)
        logger: Receives log lines from the worker's stdout

    Returns:
        List of absolute paths to the generated PNG files

    Raises:
        RuntimeError: Worker failed or produced no images
    """
    workdir = config.workdir.path
    if config.grid.grid_type == "nested":
        from workflows.infrastructure.ww3.nested_level_dirs import list_nested_level_paths

        paths = list_nested_level_paths(workdir)
        regions = list(
            config.grid.nested_levels
            or [region for region in (config.grid.outer, config.grid.inner) if region is not None]
        )
        requests = [
            (path, "structured", _region_extent(regions[index]) if index < len(regions) else None)
            for index, path in enumerate(paths)
        ]
        if not requests:
            raise RuntimeError("未找到 level* 网格目录，请先生成嵌套网格")
    else:
        mode = {"structured": "structured", "smc": "smc", "unstructured": "unst"}[config.grid.mesh_type]
        requests = [(workdir, mode, _region_extent(config.grid.outer))]

    images: list[str] = []
    for directory, mode, extent in requests:
        result = _run_worker(directory, mode, logger, extent=extent)
        images.extend(str(path) for path in result.get("images", []))
    if not images:
        raise RuntimeError("未找到可视化图片，请先生成网格")
    return images


def _region_extent(region: GridRegion | None) -> list[float] | None:
    if region is None or not region.lon or not region.lat:
        return None
    return [float(region.lon[0]), float(region.lon[1]), float(region.lat[0]), float(region.lat[1])]


def _run_worker(
    directory: Path,
    mode: str,
    logger: CoreLogger,
    *,
    extent: list[float] | None = None,
) -> dict:
    """启动 ``grid_visualization.worker`` 子进程并解析 ``WW3TOOL_VIZ`` 协议输出。

    [EN] Launch the ``grid_visualization.worker`` subprocess and parse its ``WW3TOOL_VIZ`` protocol output.
    """
    src_dir = Path(os.environ.get("WW3TOOL_ROOT") or Path(__file__).resolve().parents[3])
    env = os.environ.copy()
    previous = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(src_dir) + (os.pathsep + previous if previous else "")
    command = [
        sys.executable,
        "-u",
        "-m",
        "workflows.infrastructure.grid_visualization.worker",
        "--mode",
        mode,
        "--grid-dir",
        str(directory),
    ]
    if extent is not None:
        command.extend(["--extent", *(str(value) for value in extent)])
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        env=env,
    )
    result: dict | None = None
    assert process.stdout is not None
    for raw_line in process.stdout:
        line = raw_line.rstrip()
        if line.startswith(_LOG_PREFIX):
            logger.log(line[len(_LOG_PREFIX) :])
        elif line.startswith(_RESULT_PREFIX):
            result = json.loads(line[len(_RESULT_PREFIX) :])
    return_code = process.wait()
    if result is None:
        raise RuntimeError(f"网格可视化执行失败（返回码 {return_code}）")
    if not result.get("ok"):
        raise RuntimeError(str(result.get("error") or "网格可视化失败"))
    return result
