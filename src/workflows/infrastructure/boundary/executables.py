"""在选定 ST 可执行目录中解析 ww3_bounc / ww3_grid，禁止回退到 PATH。"""

from __future__ import annotations

import os
from pathlib import Path

from ...domain.config_models import PipelineConfig
from .errors import BoundaryError
from ...support.translations import tr


REQUIRED_BOUNDARY_TOOLS = ("ww3_grid", "ww3_bounc")


def selected_executable_dir(config: PipelineConfig, *, remote: bool) -> str:
    if remote:
        name = str(config.slurm.server_st or "").strip()
        mapping = config.slurm.server_st_versions or {}
        if name and name in mapping:
            return str(mapping[name]).strip()
        if name and mapping:
            raise BoundaryError(
                "BOUNDARY_EXECUTABLE_MISSING",
                tr("boundary_server_st_no_dir", "服务器 ST 方案 {name!r} 未在 server_st_versions 中给出可执行目录").format(name=name),
                context={"st": name},
            )
        return str(config.paths.ww3bin_path or "").strip()
    name = str(config.local_run.local_st or "").strip()
    mapping = config.local_run.local_st_versions or {}
    if name and name in mapping:
        return str(mapping[name]).strip()
    return str(config.paths.ww3bin_path or "").strip()


def resolve_in_dir(executable_dir: str, tool: str) -> str:
    directory = str(executable_dir or "").strip()
    if not directory:
        raise BoundaryError(
            "BOUNDARY_EXECUTABLE_MISSING",
            tr("boundary_exe_dir_unset", "未配置可执行目录，无法解析 {tool}").format(tool=tool),
            context={"tool": tool},
            hints=[tr("boundary_hint_set_exe_dir", "在 local_run.local_st 或 slurm.server_st 中指定可执行目录")],
        )
    root = Path(directory)
    names = [tool]
    if os.name == "nt":
        names.insert(0, tool + ".exe")
    for name in names:
        candidate = root / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate.resolve())
        if candidate.is_file() and os.name == "nt":
            return str(candidate.resolve())
    raise BoundaryError(
        "BOUNDARY_EXECUTABLE_MISSING",
        tr("boundary_exe_missing_in_dir", "选定目录缺少可执行程序 {tool}").format(tool=tool),
        context={"directory": directory, "tool": tool, "resolved_directory": str(root)},
        hints=[tr("boundary_hint_exe_fix_dir", "补充相应 WW3 程序或修正 ST 可执行目录；不会使用 PATH 中的同名程序")],
    )


def resolve_boundary_executables(config: PipelineConfig, *, remote: bool) -> dict[str, str]:
    directory = selected_executable_dir(config, remote=remote)
    resolved = {"directory": directory}
    for tool in REQUIRED_BOUNDARY_TOOLS:
        resolved[tool] = resolve_in_dir(directory, tool)
    return resolved
