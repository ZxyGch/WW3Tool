"""Slurm idle-resource selection and server.sh confirmation (shared by GUI, shell, CLI)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

from ..domain.config_models import PipelineConfig
from ..infrastructure.adapters.ww3_namelist_adapter import update_server_script
from ..support.logging import CoreLogger, LogCallback
from ..support.translations import tr
from .remote_ops import RemoteResult, run_slurm_idle_resources

IdleMode = Literal["full", "half"]


@dataclass(frozen=True)
class SlurmAllocation:
    cpu: str
    cores: int
    nodes: int


def normalize_idle_rows(rows: list[dict] | None) -> list[dict]:
    """Normalize remote idle summary rows to the shape used by the desktop panel."""
    valid: list[dict] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        cpu = str(row.get("cpu") or row.get("partition") or "").strip()
        if not cpu:
            continue
        try:
            nodes = int(row.get("nodes") or row.get("idle_nodes") or 0)
            cores = int(row.get("cores") or row.get("idle_cores") or row.get("idle_cpus") or 0)
            max_per_node = int(row.get("max_cores_per_node") or 0)
        except (TypeError, ValueError):
            continue
        if nodes <= 0 or cores <= 0:
            continue
        valid.append(
            {
                "cpu": cpu,
                "nodes": nodes,
                "cores": cores,
                "max_cores_per_node": max_per_node,
            }
        )
    valid.sort(key=lambda item: item["cores"], reverse=True)
    return valid


def select_idle_allocation(rows: list[dict], mode: IdleMode) -> SlurmAllocation:
    """Pick Slurm resources using the same rules as the desktop full/half buttons."""
    normalized = normalize_idle_rows(rows)
    if not normalized:
        raise ValueError(tr("step6_idle_resources_empty", "当前没有可用的空闲 CPU 数据，请先连接服务器或检查空闲资源"))

    best = max(normalized, key=lambda item: int(item.get("cores") or 0))
    total_cores = max(1, int(best.get("cores") or 1))
    total_nodes = max(1, int(best.get("nodes") or 1))
    max_per_node = max(
        1,
        int(best.get("max_cores_per_node") or 0)
        or ((total_cores + total_nodes - 1) // total_nodes),
    )
    if mode == "half":
        cores = max(1, (total_cores + 1) // 2)
        nodes = min(total_nodes, max(1, (cores + max_per_node - 1) // max_per_node))
    else:
        cores = total_cores
        nodes = total_nodes
    cpu = str(best.get("cpu") or "").strip()
    if not cpu:
        raise ValueError(tr("step6_idle_resources_empty", "当前没有可用的空闲 CPU 数据，请先连接服务器或检查空闲资源"))
    return SlurmAllocation(cpu=cpu, cores=cores, nodes=nodes)


def persist_slurm_params(params_path: str, allocation: SlurmAllocation) -> None:
    """Write ``slurm.cpu`` / ``cores`` / ``nodes`` back to params.yml."""
    path = Path(params_path)
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)

    def indent_of(line: str) -> int:
        return len(line) - len(line.lstrip(" "))

    slurm_start = next((i for i, line in enumerate(lines) if line.lstrip().startswith("slurm:")), None)
    if slurm_start is None:
        raise ValueError(tr("cli_slurm_section_missing", "params.yml 中缺少 slurm: 段"))

    slurm_end = len(lines)
    for i in range(slurm_start + 1, len(lines)):
        line = lines[i]
        if line.strip() and not line.lstrip().startswith("#") and indent_of(line) == 0:
            slurm_end = i
            break

    values = {
        "cpu": allocation.cpu,
        "cores": str(allocation.cores),
        "nodes": str(allocation.nodes),
    }
    updated: set[str] = set()
    for i in range(slurm_start + 1, slurm_end):
        for key, value in values.items():
            match = re.match(rf"^(\s*){re.escape(key)}\s*:.*$", lines[i])
            if match:
                lines[i] = f"{match.group(1)}{key}: {value}\n"
                updated.add(key)
                break

    insert_at = slurm_start + 1
    base_indent = indent_of(lines[slurm_start])
    field_indent = " " * (base_indent + 2)
    for key in ("cpu", "cores", "nodes"):
        if key not in updated:
            lines.insert(insert_at, f"{field_indent}{key}: {values[key]}\n")
            insert_at += 1

    slurm_end = len(lines)
    for i in range(slurm_start + 1, len(lines)):
        line = lines[i]
        if line.strip() and not line.lstrip().startswith("#") and indent_of(line) == 0:
            slurm_end = i
            break
    _ensure_cpu_in_group(lines, slurm_start, slurm_end, allocation.cpu)
    path.write_text("".join(lines), encoding="utf-8")


def _ensure_cpu_in_group(lines: list[str], slurm_start: int, slurm_end: int, cpu: str) -> None:
    """Ensure ``cpu`` appears in ``slurm.cpu_group`` when that list exists."""
    group_start = next(
        (i for i in range(slurm_start + 1, slurm_end) if lines[i].lstrip().startswith("cpu_group:")),
        None,
    )
    if group_start is None:
        return

    item_indent = " " * (len(lines[group_start]) - len(lines[group_start].lstrip(" ")) + 2)
    existing: list[str] = []
    i = group_start + 1
    while i < slurm_end and lines[i].startswith(item_indent) and lines[i].lstrip().startswith("- "):
        existing.append(lines[i].split("-", 1)[1].strip())
        i += 1
    if cpu in existing:
        return
    lines.insert(group_start + 1, f"{item_indent}- {cpu}\n")


def apply_allocation_to_config(config: PipelineConfig, allocation: SlurmAllocation) -> None:
    config.slurm.cpu = allocation.cpu
    config.slurm.cores = str(allocation.cores)
    config.slurm.nodes = str(allocation.nodes)
    group = list(config.slurm.cpu_group or [])
    if allocation.cpu and allocation.cpu not in group:
        group.insert(0, allocation.cpu)
    config.slurm.cpu_group = group


def run_slurm_idle(config: PipelineConfig, log: Optional[LogCallback] = None) -> RemoteResult:
    """Query and print Slurm idle CPU resources."""
    return run_slurm_idle_resources(config, log=log)


def run_confirm_slurm(
    config: PipelineConfig,
    params_path: str,
    log: Optional[LogCallback] = None,
    *,
    mode: IdleMode | None = None,
) -> int:
    """Apply Slurm settings to params.yml and regenerate ``server.sh``."""
    logger = CoreLogger(callback=log)

    if mode is not None:
        result = run_slurm_idle_resources(config, log=logger.log)
        if not result.success:
            return 1
        data = result.data if isinstance(result.data, dict) else {}
        rows = data.get("idle_summary") or []
        try:
            allocation = select_idle_allocation(rows, mode)
        except ValueError as exc:
            logger.log(str(exc))
            return 1
        persist_slurm_params(params_path, allocation)
        apply_allocation_to_config(config, allocation)
        action = (
            tr("step6_use_idle_half", "半数使用")
            if mode == "half"
            else tr("step6_use_idle_full", "最大化使用")
        )
        logger.log(
            tr(
                "step6_idle_resources_applied",
                "✅ 已按{mode}选择空闲资源：CPU={cpu}, 核数={cores}, 节点数={nodes}",
            ).format(mode=action, cpu=allocation.cpu, cores=allocation.cores, nodes=allocation.nodes)
        )

    update_server_script(config, logger)
    logger.log(tr("server_script_applied", "✅ server.sh 已应用 Slurm 配置"))
    return 0
