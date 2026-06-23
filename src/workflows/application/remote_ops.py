"""远程服务器 SSH 操作用例。

通过 ``config.server`` 连接远程 HPC/集群，执行上传、提交作业、下载结果、
状态检查、队列查询与清空远程目录等操作，供 CLI 远程子命令与桌面 Step 3 调用。

流水线步骤：Step 3（远程计算）— 上传、提交、监控与结果回收。

安全约定
--------
* ``run_upload`` 与 ``run_clear_remote`` 为**破坏性**操作，必须传入
  ``confirmed=True`` 才会执行；CLI 通过 ``--confirm`` 强制确认。
* 其余命令为只读或增量写入，可自由调用。

输入/输出
---------
- 输入：``PipelineConfig``（``server.*`` 与 ``workdir``）
- 输出：``RemoteResult``（成功标志、日志消息、可选附加数据）
"""

from __future__ import annotations

import os
import posixpath
import shlex
import hashlib
import re
import base64
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from ..domain.config_models import PipelineConfig
from ..infrastructure.remote.ssh_client import SshClient
from ..infrastructure.runtime_config import PUBLIC_DIR
from ..support.logging import CoreLogger, LogCallback
from ..support.translations import tr


@dataclass
class RemoteResult:
    """远程 SSH 操作的统一返回结构。

    Attributes:
        success: 操作是否成功完成。
        messages: 执行过程中的日志消息列表。
        data: 可选附加数据（如任务状态字符串、下载文件列表、队列输出）。
        error: 失败时的错误描述；成功时为 ``None``。
    """

    success: bool = True
    messages: List[str] = field(default_factory=list)
    data: Optional[object] = None
    error: Optional[str] = None


def _make_client(config: PipelineConfig) -> SshClient:
    """根据 ``config.server`` 构造 SSH 客户端实例。"""
    return SshClient(config.server)


def _acquire(config: PipelineConfig, existing: Optional[SshClient] = None):
    """返回 ``(client, owns)`` —— 若传入已连接的 client 则复用，否则新建。"""
    if existing is not None:
        return existing, False
    return _make_client(config), True


def _resolve_remote_dir(config: PipelineConfig) -> str:
    """解析并校验远程工作目录路径。

    优先使用 ``server.remote_dir``（第六步输入框写入的实际路径）；
    为空时回退到 ``server.default_remote_dir`` + 工作目录名。

    无论来源如何，若路径末段与工作目录名不匹配，自动追加工作目录名，
    确保始终指向具体的 per-case 远程目录。
    """
    remote_dir = config.server.remote_dir.strip()
    workdir_name = config.workdir.path.name if config.workdir.path else ""

    if not remote_dir:
        base = config.server.default_remote_dir.strip()
        if not base:
            raise ValueError(
                tr("remote_dir_missing", "❌ server.remote_dir 和 server.default_remote_dir 均未配置。请在 params.yml 的 server: 段填写远程工作目录。")
            )
        if workdir_name:
            tail = posixpath.basename(base.rstrip("/"))
            remote_dir = base.rstrip("/") if tail == workdir_name else posixpath.join(base.rstrip("/"), workdir_name)
        else:
            remote_dir = base
    elif workdir_name:
        # remote_dir 非空但未包含工作目录名 → 自动追加
        tail = posixpath.basename(remote_dir.rstrip("/"))
        if tail != workdir_name:
            remote_dir = posixpath.join(remote_dir.rstrip("/"), workdir_name)

    if config.server.user and (remote_dir == "~" or remote_dir.startswith("~/")):
        remote_dir = f"/home/{config.server.user}{remote_dir[1:]}"
    return remote_dir


def _resolve_local_dir(config: PipelineConfig) -> str:
    """返回本地工作目录的字符串形式。"""
    return str(config.workdir.path)


# ── 连接测试 ────────────────────────────────────────────────────────────

def run_connect_test(
    config: PipelineConfig,
    log: Optional[LogCallback] = None,
    *,
    client: Optional[SshClient] = None,
) -> RemoteResult:
    """测试 SSH 连通性并输出服务器基本信息（hostname、内核、uptime）。

    Args:
        config: 流水线配置（``server.*`` 连接参数）。
        log: 可选日志回调。

    Returns:
        连接成功时 ``success=True``；异常时 ``success=False`` 并填充 ``error``。
    """
    logger = CoreLogger(callback=log)
    c, owns = _acquire(config, client)
    try:
        if owns:
            c.connect(log=logger.log)
        out, _, _ = c.exec_command("hostname && uname -r && uptime", log=logger.log)
        for line in out.splitlines():
            logger.log(line)
        return RemoteResult(success=True, messages=list(logger.messages))
    except Exception as exc:
        return RemoteResult(success=False, error=str(exc), messages=list(logger.messages))
    finally:
        if owns:
            c.close()


# ── 上传（破坏性 — 需 confirmed=True）──────────────────────────────────

def run_upload(
    config: PipelineConfig,
    log: Optional[LogCallback] = None,
    *,
    confirmed: bool = False,
    client: Optional[SshClient] = None,
) -> RemoteResult:
    """将本地工作目录完整上传至远程服务器。

    **必须传入 ``confirmed=True``**；否则立即返回错误，防止误触发上传。

    Args:
        config: 流水线配置。
        log: 可选日志回调。
        confirmed: 显式确认标志；CLI 对应 ``--confirm``。

    Returns:
        上传成功或失败对应的 ``RemoteResult``。
    """
    logger = CoreLogger(callback=log)
    if not confirmed:
        msg = (
            tr("upload_blocked_confirm_required", "⚠️ 上传被阻止：这是破坏性操作，必须显式传入 confirmed=True（CLI: --confirm）才能执行。")
        )
        logger.log(tr("error_prefix", "❌ {message}").format(message=msg))
        return RemoteResult(success=False, error=msg, messages=list(logger.messages))

    c, owns = _acquire(config, client)
    try:
        remote_dir = _resolve_remote_dir(config)
        local_dir = _resolve_local_dir(config)
        if not os.path.isdir(local_dir):
            raise FileNotFoundError(tr("local_workdir_not_exists", "❌ 本地工作目录不存在：{path}").format(path=local_dir))
        if owns:
            c.connect(log=logger.log)
        c.upload_folder(local_dir, remote_dir, log=logger.log)
        return RemoteResult(success=True, messages=list(logger.messages))
    except Exception as exc:
        logger.log(tr("upload_failed", "❌ 上传失败：{error}").format(error=exc))
        return RemoteResult(success=False, error=str(exc), messages=list(logger.messages))
    finally:
        if owns:
            c.close()


def _forcing_excluded_relpaths(config: PipelineConfig, local_dir: str) -> set[str]:
    local_root = os.path.realpath(local_dir)
    excluded: set[str] = set()

    def add_path(path: object) -> None:
        if not path:
            return
        real = os.path.realpath(os.fspath(path))
        if not os.path.isfile(real):
            return
        try:
            common = os.path.commonpath([local_root, real])
        except ValueError:
            return
        if common != local_root:
            return
        excluded.add(os.path.relpath(real, local_root).replace(os.sep, "/"))

    for path in (
        config.forcing.wind,
        config.forcing.current,
        config.forcing.level,
        config.forcing.ice,
    ):
        add_path(path)

    try:
        from ..infrastructure.forcing.file_service import FileService

        scanned = FileService().scan_forcing_files(
            local_dir,
            auto_associate=config.forcing.auto_associate is not False,
        )
        for _field, path in scanned.existing_items():
            add_path(path)
    except Exception:
        pass
    return excluded


def run_upload_without_forcing(
    config: PipelineConfig,
    log: Optional[LogCallback] = None,
    *,
    confirmed: bool = False,
    client: Optional[SshClient] = None,
) -> RemoteResult:
    """Upload local workdir files except configured/detected forcing files."""
    logger = CoreLogger(callback=log)
    if not confirmed:
        msg = tr("upload_without_forcing_blocked_confirm_required", "上传非强迫场文件被阻止：必须显式确认后才能执行。")
        logger.log(tr("error_prefix", "❌ {message}").format(message=msg))
        return RemoteResult(success=False, error=msg, messages=list(logger.messages))

    c, owns = _acquire(config, client)
    try:
        remote_dir = _resolve_remote_dir(config)
        local_dir = _resolve_local_dir(config)
        if not os.path.isdir(local_dir):
            raise FileNotFoundError(tr("local_workdir_not_exists", "❌ 本地工作目录不存在：{path}").format(path=local_dir))
        if owns:
            c.connect(log=logger.log)
        excluded = _forcing_excluded_relpaths(config, local_dir)
        if excluded:
            logger.log(
                tr(
                    "upload_without_forcing_excluding",
                    "ℹ️ 将跳过 {count} 个强迫场文件",
                ).format(count=len(excluded))
            )
        logger.log(tr("upload_without_forcing_start", "📤 开始上传非强迫场文件到 {path} ...").format(path=remote_dir))
        count = c.upload_matching_files(
            local_dir,
            remote_dir,
            lambda relpath: relpath.replace("\\", "/") not in excluded,
            recursive=True,
            log=logger.log,
        )
        if count == 0:
            logger.log(tr("upload_without_forcing_none", "⚠️ 没有可上传的非强迫场文件"))
        else:
            logger.log(tr("upload_without_forcing_done", "✅ 已上传 {count} 个非强迫场文件 → {path}").format(count=count, path=remote_dir))
        return RemoteResult(success=True, data=count, messages=list(logger.messages))
    except Exception as exc:
        logger.log(tr("upload_without_forcing_failed", "❌ 上传非强迫场文件失败：{error}").format(error=exc))
        return RemoteResult(success=False, error=str(exc), messages=list(logger.messages))
    finally:
        if owns:
            c.close()


def _parse_sinfo_idle_resources(out: str) -> dict:
    """Parse ``sinfo -N`` output into idle/mixed node and CPU counts."""
    idle_nodes: list[dict] = []
    mixed_nodes: list[dict] = []
    idle_summary: list[dict] = []
    all_partitions: set[str] = set()
    total_idle_cpus = 0
    total_idle_nodes = 0

    def partitions(value: str) -> list[str]:
        parts = []
        for part in value.replace(",", " ").split():
            name = part.strip().rstrip("*")
            if name:
                parts.append(name)
        return parts or [tr("unknown_cpu_partition", "未知")]

    def append_summary(record: dict) -> None:
        idle_cpus = int(record.get("idle_cpus") or 0)
        if idle_cpus <= 0:
            return
        for cpu_name in partitions(str(record.get("partition") or "")):
            idle_summary.append(
                {
                    "cpu": cpu_name,
                    "nodes": 1,
                    "cores": idle_cpus,
                    "max_cores_per_node": idle_cpus,
                }
            )

    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("|")
        if len(parts) < 5:
            continue
        node, state, cpus_text, cpu_state, partition = [part.strip() for part in parts[:5]]
        state_l = state.lower().strip("*")
        try:
            cpus = int(cpus_text)
        except ValueError:
            cpus = 0
        all_partitions.update(partitions(partition))
        alloc = idle = other = total = 0
        cpu_parts = cpu_state.split("/")
        if len(cpu_parts) == 4:
            try:
                alloc, idle, other, total = [int(value) for value in cpu_parts]
            except ValueError:
                idle = 0
                total = cpus
        else:
            total = cpus
            idle = cpus if "idle" in state_l else 0
        if total == 0:
            total = cpus
        record = {
            "node": node,
            "state": state,
            "partition": partition.rstrip("*"),
            "cpus": cpus,
            "alloc_cpus": alloc,
            "idle_cpus": idle,
            "other_cpus": other,
            "total_cpus": total,
        }
        if "idle" in state_l:
            total_idle_nodes += 1
            total_idle_cpus += idle or total or cpus
            idle_nodes.append(record)
            append_summary(record)
        elif idle > 0 and any(token in state_l for token in ("mix", "alloc")):
            total_idle_cpus += idle
            mixed_nodes.append(record)
            append_summary(record)
    idle_summary.sort(
        key=lambda item: (item["cores"], item["cpu"]),
        reverse=True,
    )
    return {
        "idle_nodes": total_idle_nodes,
        "idle_cpus": total_idle_cpus,
        "idle_summary": idle_summary,
        "partitions": sorted(all_partitions),
        "idle_node_details": idle_nodes,
        "mixed_node_details": mixed_nodes,
    }


def run_slurm_idle_resources(
    config: PipelineConfig,
    log: Optional[LogCallback] = None,
    *,
    client: Optional[SshClient] = None,
) -> RemoteResult:
    """Query Slurm idle nodes and idle CPU count using ``sinfo``."""
    logger = CoreLogger(callback=log)
    c, owns = _acquire(config, client)
    try:
        if owns:
            c.connect(log=logger.log)
        cmd = "sinfo -h -N -o '%N|%T|%c|%C|%P'"
        out, err, code = c.exec_command(cmd, timeout=10)
        if code != 0:
            raise RuntimeError(err or out or tr("remote_command_exit_code", "远程命令退出码 {code}").format(code=code))
        if err:
            logger.log(tr("sinfo_cmd_warning", "⚠️ sinfo 警告: {error}").format(error=err))
        data = _parse_sinfo_idle_resources(out)
        logger.log(
            tr(
                "slurm_idle_summary",
                "🧮 Slurm 空闲资源：空闲节点 {nodes} 个，可用空闲 CPU {cpus} 个",
            ).format(nodes=data["idle_nodes"], cpus=data["idle_cpus"])
        )
        details = [*data["idle_node_details"], *data["mixed_node_details"]]
        if details:
            logger.log(tr("slurm_idle_nodes_header", "📍 空闲 CPU 所在节点："))
            for item in details[:80]:
                logger.log(
                    "  {partition} {node}: {idle}/{total} CPU idle ({state})".format(
                        partition=item["partition"],
                        node=item["node"],
                        idle=item["idle_cpus"],
                        total=item["total_cpus"] or item["cpus"],
                        state=item["state"],
                    )
                )
            if len(details) > 80:
                logger.log(tr("slurm_idle_nodes_more", "  ... 还有 {count} 个节点未显示").format(count=len(details) - 80))
        else:
            logger.log(tr("slurm_no_idle_resources", "⚠️ 当前未发现空闲 Node/CPU"))
        return RemoteResult(success=True, data=data, messages=list(logger.messages))
    except Exception as exc:
        logger.log(tr("slurm_idle_failed", "❌ 检查 Slurm 空闲资源失败：{error}").format(error=exc))
        return RemoteResult(success=False, error=str(exc), data=None, messages=list(logger.messages))
    finally:
        if owns:
            c.close()


# ── 节点状态 ────────────────────────────────────────────────────────────

def _node_cpu_bar(record: dict) -> str:
    bar = "█" * int(record.get("idle_cpus") or 0) + "░" * int(record.get("alloc_cpus") or 0)
    other = int(record.get("other_cpus") or 0)
    if other > 0:
        bar += "·" * other
    return bar


def _format_node_status_lines(nodes: list[dict], *, indent: str = "  ") -> list[str]:
    """Format per-node status rows with fixed column widths for log alignment."""
    if not nodes:
        return []

    name_w = max(len(str(n["node"])) for n in nodes)
    part_w = max(len(str(n["partition"])) for n in nodes)
    idle_w = max(len(str(n["idle_cpus"])) for n in nodes)
    total_w = max(len(str(n["total_cpus"] or n["cpus"])) for n in nodes)

    lines: list[str] = []
    for n in nodes:
        total = n["total_cpus"] or n["cpus"]
        lines.append(
            f"{indent}{n['node']:<{name_w}}  "
            f"[{n['partition']:<{part_w}}]  "
            f"{n['idle_cpus']:>{idle_w}}/{total:<{total_w}}  "
            f"{_node_cpu_bar(n)}"
        )
    return lines

def _parse_all_nodes(out: str) -> list[dict]:
    """Parse ``sinfo -N`` output into a list of ALL nodes with CPU status."""
    nodes: list[dict] = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("|")
        if len(parts) < 5:
            continue
        node, state, cpus_text, cpu_state, partition = [p.strip() for p in parts[:5]]
        state_l = state.lower().strip("*")
        try:
            cpus = int(cpus_text)
        except ValueError:
            cpus = 0
        alloc = idle = other = total = 0
        cpu_parts = cpu_state.split("/")
        if len(cpu_parts) == 4:
            try:
                alloc, idle, other, total = [int(v) for v in cpu_parts]
            except ValueError:
                total = cpus
        else:
            total = cpus
            idle = cpus if "idle" in state_l else 0
        if total == 0:
            total = cpus
        # [EN] Categorize: idle / mixed / allocated / down / other
        if "idle" in state_l:
            category = "idle"
        elif "mix" in state_l:
            category = "mixed"
        elif "alloc" in state_l:
            category = "allocated"
        elif "down" in state_l or "drain" in state_l:
            category = "down"
        else:
            category = "other"
        nodes.append({
            "node": node,
            "state": state,
            "category": category,
            "partition": partition.rstrip("*"),
            "cpus": cpus,
            "alloc_cpus": alloc,
            "idle_cpus": idle,
            "other_cpus": other,
            "total_cpus": total,
        })
    return nodes


def run_node_status(
    config: PipelineConfig,
    log: Optional[LogCallback] = None,
    *,
    client: Optional[SshClient] = None,
) -> RemoteResult:
    """Query and display every Slurm node with per-node CPU status."""
    logger = CoreLogger(callback=log)
    c, owns = _acquire(config, client)
    try:
        if owns:
            c.connect(log=logger.log)
        cmd = "sinfo -h -N -o '%N|%T|%c|%C|%P'"
        out, err, code = c.exec_command(cmd, timeout=10)
        if code != 0:
            raise RuntimeError(err or out or tr("remote_command_exit_code", "远程命令退出码 {code}").format(code=code))
        if err:
            logger.log(tr("sinfo_cmd_warning", "⚠️ sinfo 警告: {error}").format(error=err))
        nodes = _parse_all_nodes(out)
        # [EN] Summary counts
        counts: dict[str, int] = {}
        for n in nodes:
            counts[n["category"]] = counts.get(n["category"], 0) + 1
        total_idle_cpus = sum(n["idle_cpus"] for n in nodes)
        total_alloc_cpus = sum(n["alloc_cpus"] for n in nodes)
        logger.log(
            tr("node_status_summary",
               "🖥️ 集群节点概览：共 {total} 个节点 | 空闲 {idle} · 混合 {mixed} · 已分配 {alloc} · 离线 {down}").format(
                total=len(nodes),
                idle=counts.get("idle", 0),
                mixed=counts.get("mixed", 0),
                alloc=counts.get("allocated", 0),
                down=counts.get("down", 0),
            )
        )
        logger.log(
            tr("node_status_cpu_summary",
               "   CPU：空闲 {idle} 核 · 已分配 {alloc} 核").format(
                idle=total_idle_cpus, alloc=total_alloc_cpus
            )
        )
        # [EN] Per-node detail
        logger.log(tr("node_status_detail_header", "📍 节点详情："))
        for line in _format_node_status_lines(nodes):
            logger.log(line)
        return RemoteResult(success=True, data={"nodes": nodes, "counts": counts}, messages=list(logger.messages))
    except Exception as exc:
        logger.log(tr("node_status_failed", "❌ 查询节点状态失败：{error}").format(error=exc))
        return RemoteResult(success=False, error=str(exc), data=None, messages=list(logger.messages))
    finally:
        if owns:
            c.close()


def run_submit(
    config: PipelineConfig,
    log: Optional[LogCallback] = None,
    *,
    script: str = "server.sh",
    client: Optional[SshClient] = None,
) -> RemoteResult:
    """在远程工作目录中执行提交脚本（默认 ``server.sh``）。

    Args:
        config: 流水线配置。
        log: 可选日志回调。
        script: 远程执行的脚本文件名。

    Returns:
        脚本退出码为 0 时 ``success=True``；非零时 ``error`` 含退出码说明。
    """
    logger = CoreLogger(callback=log)
    c, owns = _acquire(config, client)
    try:
        remote_dir = _resolve_remote_dir(config)
        if owns:
            c.connect(log=logger.log)
        code = c.exec_script(script, remote_dir, log=logger.log)
        return RemoteResult(
            success=(code == 0),
            error=None if code == 0 else tr("remote_script_exit_code_plain", "❌ 脚本退出码 {code}").format(code=code),
            messages=list(logger.messages),
        )
    except Exception as exc:
        logger.log(tr("submit_failed", "❌ 提交失败：{error}").format(error=exc))
        return RemoteResult(success=False, error=str(exc), messages=list(logger.messages))
    finally:
        if owns:
            c.close()


# ── 状态检查 ────────────────────────────────────────────────────────────

def run_check_status(
    config: PipelineConfig,
    log: Optional[LogCallback] = None,
    *,
    client: Optional[SshClient] = None,
) -> RemoteResult:
    """检查远程作业是否已完成（检测 ``success`` / ``fail`` 标记文件）。

    Args:
        config: 流水线配置。
        log: 可选日志回调。

    Returns:
        ``data`` 字段为状态字符串：``"success"``、``"failed"`` 或 ``"running"``。
    """
    logger = CoreLogger(callback=log)
    c, owns = _acquire(config, client)
    try:
        remote_dir = _resolve_remote_dir(config)
        if owns:
            c.connect(log=logger.log)
        status = c.check_completion(remote_dir, log=logger.log)
        msg_map = {
            "success": tr("remote_status_success", "✅ 检测到 success 标记，计算已完成"),
            "failed": tr("remote_status_failed", "❌ 检测到 fail 标记，计算失败"),
            "running": tr("remote_status_running", "⏳ 未检测到结束标志，计算仍在进行"),
        }
        logger.log(msg_map.get(status, status))
        return RemoteResult(success=True, data=status, messages=list(logger.messages))
    except Exception as exc:
        logger.log(tr("remote_status_check_failed", "❌ 状态检查失败：{error}").format(error=exc))
        return RemoteResult(success=False, error=str(exc), messages=list(logger.messages))
    finally:
        if owns:
            c.close()


def _ntfy_topic_for(config: PipelineConfig, remote_dir: str) -> str:
    digest = hashlib.sha1(remote_dir.encode("utf-8")).hexdigest()[:16]
    return f"ww3-{digest}"


def run_check_ntfy_status(
    config: PipelineConfig,
    log: Optional[LogCallback] = None,
    *,
    client: Optional[SshClient] = None,
) -> RemoteResult:
    """检查远程服务器上 ntfy 常驻 watcher 是否正在运行。

    通过检查 ``ntfy_watch.pid`` 文件和 ``kill -0`` 验证进程存活。

    Returns:
        ``data`` 为 ``{"running": bool, "pid": str|None, "topic": str}``。
    """
    logger = CoreLogger(callback=log)
    c, owns = _acquire(config, client)
    try:
        remote_dir = _resolve_remote_dir(config)
        topic = _ntfy_topic_for(config, remote_dir)
        if owns:
            c.connect(log=logger.log)
        pid_file = "ntfy_watch.pid"
        mode_file = "ntfy_watch.pid.mode"
        q_remote = shlex.quote(remote_dir)
        command = (
            f"cd {q_remote} && "
            f"if [ -f {pid_file} ]; then "
            f"PID=$(cat {pid_file}); "
            f"MODE=$(cat {mode_file} 2>/dev/null); "
            f"if kill -0 $PID 2>/dev/null && [ \"$MODE\" = 'all' ]; then "
            f"echo \"RUNNING $PID\"; "
            f"else "
            f"echo \"STOPPED\"; "
            f"fi; "
            f"else "
            f"echo \"STOPPED\"; "
            f"fi"
        )
        out, err, code = c.exec_command(command, timeout=10)
        running = False
        pid = None
        if out and out.strip().startswith("RUNNING"):
            running = True
            parts = out.strip().split()
            pid = parts[1] if len(parts) > 1 else "unknown"
        logger.log(
            tr("ntfy_status_running", "✅ ntfy watcher 正在运行 (PID: {pid})").format(pid=pid)
            if running
            else tr("ntfy_status_stopped", "⏹ ntfy watcher 未运行")
        )
        return RemoteResult(
            success=True,
            data={"running": running, "pid": pid, "topic": topic},
            messages=list(logger.messages),
        )
    except Exception as exc:
        logger.log(tr("ntfy_status_check_failed", "❌ 检查 ntfy 状态失败：{error}").format(error=exc))
        return RemoteResult(
            success=False,
            error=str(exc),
            data={"running": False, "pid": None, "topic": ""},
            messages=list(logger.messages),
        )
    finally:
        if owns:
            c.close()


def run_send_ntfy_test(
    config: PipelineConfig,
    log: Optional[LogCallback] = None,
    *,
    topic: str | None = None,
    client: Optional[SshClient] = None,
) -> RemoteResult:
    """通过远程服务器上已运行的 ntfy watcher 发送一条测试通知。

    在服务器端执行 ``curl -d`` 向 ntfy.sh 发送测试消息，用于验证
    watcher 的网络连通性和通知链路。

    Returns:
        ``data`` 为 ``{"topic": str}``。
    """
    logger = CoreLogger(callback=log)
    c, owns = _acquire(config, client)
    try:
        remote_dir = _resolve_remote_dir(config)
        topic = (topic or _ntfy_topic_for(config, remote_dir)).strip()
        label = "WW3"
        if owns:
            c.connect(log=logger.log)
        host_check_cmd = "hostname 2>/dev/null || echo unknown"
        host_out, _, _ = c.exec_command(host_check_cmd, timeout=5)
        host = host_out.strip() if host_out else "unknown"
        # [EN] Build curl command with proper quoting for remote bash execution.
        # 构造 curl 命令，确保远程 bash 引号正确
        q_topic = shlex.quote(topic)
        q_host = shlex.quote(host)
        q_title = shlex.quote(f"Title: {label} test")
        q_url = shlex.quote(f"https://ntfy.sh/{topic}")
        curl_cmd = (
            f"body=$(printf 'Test from %s\\nTopic: %s\\nTime: %s' "
            f"{q_host} {q_topic} \"$(date '+%F %T')\") && "
            f"curl -fsS --connect-timeout 10 --max-time 30 "
            f"-H {q_title} "
            f"-H 'Tags: test,ocean' "
            f"-d \"$body\" "
            f"{q_url}"
        )
        logger.log(
            tr("ntfy_test_sending", "📤 正在从服务器 {host} 发送测试通知到 topic: {topic}").format(
                host=host, topic=topic
            )
        )
        out, err, code = c.exec_command(curl_cmd, timeout=40)
        if code == 0:
            logger.log(
                tr("ntfy_test_sent", "✅ 测试通知已发送，请检查 ntfy.sh/{topic}").format(topic=topic)
            )
        else:
            err_msg = err.strip() if err else (out.strip() if out else f"exit code {code}")
            logger.log(
                tr("ntfy_test_failed", "❌ 测试通知发送失败：{error}").format(error=err_msg)
            )
            return RemoteResult(
                success=False,
                error=err_msg,
                data={"topic": topic},
                messages=list(logger.messages),
            )
        return RemoteResult(
            success=True,
            data={"topic": topic},
            messages=list(logger.messages),
        )
    except Exception as exc:
        logger.log(tr("ntfy_test_failed", "❌ 测试通知发送失败：{error}").format(error=exc))
        return RemoteResult(success=False, error=str(exc), messages=list(logger.messages))
    finally:
        if owns:
            c.close()


def run_inject_ntfy_listener(
    config: PipelineConfig,
    log: Optional[LogCallback] = None,
    *,
    topic: str | None = None,
    interval: int = 60,
    timeout_hours: int = 0,
    mode: str = "all",
    job_id: str | None = None,
    client: Optional[SshClient] = None,
) -> RemoteResult:
    """Upload and start a login-node ntfy watcher."""
    logger = CoreLogger(callback=log)
    c, owns = _acquire(config, client)
    try:
        remote_dir = _resolve_remote_dir(config)
        topic = (topic or _ntfy_topic_for(config, remote_dir)).strip()
        label = "WW3"
        mode = "once" if mode == "once" else "all"
        job_id = str(job_id or "").strip()
        if mode == "once" and not job_id:
            raise ValueError(tr("ntfy_job_id_required", "❌ 请填写要监听的 Slurm 任务 ID"))
        scripts_dir = os.path.join(PUBLIC_DIR, "scripts")
        watcher = os.path.join(scripts_dir, "ww3_ntfy_watch.sh")
        if not os.path.isfile(watcher):
            raise FileNotFoundError(
                tr("ntfy_watcher_missing", "❌ 未找到 ntfy 监听脚本：{path}").format(path=watcher)
            )
        if owns:
            c.connect(log=logger.log)
        # [EN] Write the script directly to remote /tmp via base64 (no SFTP upload, no workdir copy).
        logger.log(
            tr("ntfy_deploying_watcher", "📤 正在部署 ntfy 监听脚本到远程 /tmp")
        )
        with open(watcher, "rb") as f:
            b64_payload = base64.b64encode(f.read()).decode("ascii")
        remote_script = "/tmp/ww3_ntfy_watch.sh"
        q_script = shlex.quote(remote_script)
        q_remote = shlex.quote(remote_dir)
        q_topic = shlex.quote(topic)
        q_label = shlex.quote(label)
        q_mode = shlex.quote(mode)
        q_jobs = shlex.quote(job_id) if job_id else "''"
        q_workdirs = q_remote if mode == "all" else "''"
        q_topic_line = shlex.quote(f"ntfy topic: {topic}")
        q_url_line = shlex.quote(f"ntfy url: https://ntfy.sh/{topic}")
        pid_file = "ntfy_watch.pid" if mode == "all" else f"ntfy_watch_{job_id}.pid"
        log_file = "ntfy_watch.log" if mode == "all" else f"ntfy_watch_{job_id}.log"
        mode_file = f"{pid_file}.mode"
        q_pid_file = shlex.quote(pid_file)
        q_log_file = shlex.quote(log_file)
        q_mode_file = shlex.quote(mode_file)
        command = (
            f"echo '{b64_payload}' | base64 -d > {q_script} && "
            f"chmod +x {q_script} && "
            f"cd {q_remote} && "
            f"if [ -f {q_pid_file} ] && kill -0 $(cat {q_pid_file}) 2>/dev/null "
            f"&& [ \"$(cat {q_mode_file} 2>/dev/null)\" = {q_mode} ]; then "
            f"echo \"ntfy watcher already running: $(cat {q_pid_file})\"; "
            "else "
            f"if [ -f {q_pid_file} ] && kill -0 $(cat {q_pid_file}) 2>/dev/null; then "
            f"kill $(cat {q_pid_file}) 2>/dev/null || true; "
            "fi; "
            f"nohup {q_script} --topic {q_topic} --label {q_label} --mode {q_mode} "
            f"--jobs {q_jobs} --workdirs {q_workdirs} --interval {int(interval)} --timeout-hours {int(timeout_hours)} "
            f"> {q_log_file} 2>&1 & echo $! > {q_pid_file}; disown; "
            f"printf '%s\\n' {q_mode} > {q_mode_file}; "
            f"echo \"ntfy watcher started: $(cat {q_pid_file})\"; "
            "fi; "
            f"printf '%s\\n' {q_topic_line}; "
            f"printf '%s\\n' {q_url_line}"
        )
        out, err, code = c.exec_command(command, timeout=20)
        if out:
            for line in out.splitlines():
                logger.log(line)
        if err:
            for line in err.splitlines():
                logger.log(f"[stderr] {line}")
        if code != 0:
            raise RuntimeError(
                err or out or tr("remote_command_exit_code", "远程命令退出码 {code}").format(code=code)
            )
        logger.log(
            tr(
                "ntfy_listener_injected",
                "✅ ntfy 监听已启动；请订阅 topic：{topic}",
            ).format(topic=topic)
        )
        return RemoteResult(success=True, data={"topic": topic}, messages=list(logger.messages))
    except Exception as exc:
        logger.log(tr("ntfy_listener_failed", "❌ 注入 ntfy 监听失败：{error}").format(error=exc))
        return RemoteResult(success=False, error=str(exc), messages=list(logger.messages))
    finally:
        if owns:
            c.close()


def run_inject_ntfy_job_listener(
    config: PipelineConfig,
    job_id: str,
    log: Optional[LogCallback] = None,
    *,
    topic: str | None = None,
    interval: int = 60,
    client: Optional[SshClient] = None,
) -> RemoteResult:
    """Upload and start a one-shot ntfy watcher for one Slurm job."""
    # [EN] Generate a per-job topic so it doesn't collide with the global listener.
    # 为单个任务生成独立 topic，避免与全局监听共用同一频道。
    if topic is None:
        remote_dir = _resolve_remote_dir(config)
        base_topic = _ntfy_topic_for(config, remote_dir)
        safe_id = re.sub(r"[^A-Za-z0-9_-]+", "-", job_id.strip()).strip("-")
        topic = f"{base_topic}-job-{safe_id}"
    return run_inject_ntfy_listener(
        config,
        log=log,
        topic=topic,
        interval=interval,
        timeout_hours=0,
        mode="once",
        job_id=job_id,
        client=client,
    )


def run_queue_status(
    config: PipelineConfig,
    log: Optional[LogCallback] = None,
    *,
    client: Optional[SshClient] = None,
) -> RemoteResult:
    """在远程服务器执行 ``squeue -l`` 并记录任务队列输出。

    Args:
        config: 流水线配置。
        log: 可选日志回调。

    Returns:
        ``data`` 字段为 ``squeue`` 原始输出文本（队列为空时为空字符串）。
    """
    logger = CoreLogger(callback=log)
    c, owns = _acquire(config, client)
    try:
        if owns:
            c.connect(log=logger.log)
        output = c.queue_status(log=logger.log)
        if output:
            logger.log(tr("queue_header_with_output", "📋 任务队列（squeue -l）：\n{output}\n{line}").format(output=output, line="=" * 46))
        else:
            logger.log(tr("queue_empty", "📋 任务队列为空（当前没有运行中的任务）"))
        return RemoteResult(success=True, data=output, messages=list(logger.messages))
    except Exception as exc:
        logger.log(tr("queue_query_failed", "❌ 查询队列失败：{error}").format(error=exc))
        return RemoteResult(success=False, error=str(exc), messages=list(logger.messages))
    finally:
        if owns:
            c.close()


def _parse_sacct_cpu_data(out: str) -> list:
    """解析 sacct -a -s RUNNING 输出，按用户聚合 CPU / 节点 / 最长运行时间。

    Returns:
        ``[[user, cpus, nodes, elapsed], ...]`` 按 CPU 数降序。
    """
    user_data: dict = {}
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("|")
        if len(parts) < 5:
            continue
        jobid, user, cpus_str, elapsed, nodelist = (
            parts[0].strip(),
            parts[1].strip(),
            parts[2].strip(),
            parts[3].strip(),
            parts[4].strip(),
        )
        # [EN] Skip sub-job entries (.batch, .ext+, .0, etc.)
        # 跳过子作业条目
        if "." in jobid:
            continue
        try:
            cpus = int(cpus_str)
        except ValueError:
            continue
        # [EN] Count nodes from compressed notation (e.g. node[1-4] → 4)
        # 从压缩记号计算节点数
        node_count = _count_nodes(nodelist)
        if user not in user_data:
            user_data[user] = {
                "cpus": 0,
                "nodes": 0,
                "elapsed": elapsed,
                "elapsed_sec": _elapsed_to_seconds(elapsed),
            }
        user_data[user]["cpus"] += cpus
        user_data[user]["nodes"] += node_count
        sec = _elapsed_to_seconds(elapsed)
        if sec > user_data[user]["elapsed_sec"]:
            user_data[user]["elapsed"] = elapsed
            user_data[user]["elapsed_sec"] = sec
    result = []
    for user, data in sorted(
        user_data.items(), key=lambda x: x[1]["cpus"], reverse=True
    ):
        result.append([user, str(data["cpus"]), str(data["nodes"]), _normalize_elapsed(data["elapsed"])])
    return result


def _count_nodes(nodelist: str) -> int:
    """从 Slurm 压缩节点列表计算节点数。如 ``node[1-4,7]`` → 5。"""
    import re

    if not nodelist or nodelist == "None":
        return 0
    total = 0
    # [EN] Split by comma outside brackets
    # 按括号外的逗号拆分
    parts = re.split(r",(?![^\[]*\])", nodelist)
    for part in parts:
        m = re.search(r"\[([^\]]+)\]", part)
        if m:
            ranges = m.group(1).split(",")
            for r in ranges:
                if "-" in r:
                    lo, hi = r.split("-", 1)
                    try:
                        total += int(hi) - int(lo) + 1
                    except ValueError:
                        total += 1
                else:
                    total += 1
        else:
            total += 1
    return total


def _elapsed_to_seconds(elapsed: str) -> int:
    """将 Slurm elapsed 字符串 (D-HH:MM:SS 或 HH:MM:SS) 转换为秒数。"""
    try:
        days = 0
        if "-" in elapsed:
            d_str, elapsed = elapsed.split("-", 1)
            days = int(d_str)
        parts = elapsed.split(":")
        if len(parts) == 3:
            return days * 86400 + int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        elif len(parts) == 2:
            return days * 86400 + int(parts[0]) * 60 + int(parts[1])
        return days * 86400
    except (ValueError, IndexError):
        return 0


def _normalize_elapsed(elapsed: str) -> str:
    """将 Slurm elapsed 字符串统一为 DD-HH:MM:SS 格式，确保位数对齐。

    Examples:
        '6-10:26:27'  → '06-10:26:27'
        '03:28:20'    → '00-03:28:20'
        '45:12'       → '00-00:45:12'
    """
    try:
        days = 0
        rest = elapsed
        if "-" in rest:
            d_str, rest = rest.split("-", 1)
            days = int(d_str)
        parts = rest.split(":")
        if len(parts) == 3:
            h, m, s = int(parts[0]), int(parts[1]), int(parts[2])
        elif len(parts) == 2:
            h, m, s = 0, int(parts[0]), int(parts[1])
        else:
            h, m, s = 0, 0, int(parts[0]) if parts[0] else 0
        return f"{days:02d}-{h:02d}:{m:02d}:{s:02d}"
    except (ValueError, IndexError):
        return elapsed


def run_cpu_ranking(
    config: PipelineConfig,
    log: Optional[LogCallback] = None,
    *,
    client: Optional[SshClient] = None,
) -> RemoteResult:
    """获取集群运行中作业的 CPU 占用情况（sacct -a -s RUNNING），按用户聚合。

    Returns:
        ``data`` 字段为 ``[[user, cpus, nodes, elapsed], ...]`` 列表，按 CPU 数降序。
    """
    logger = CoreLogger(callback=log)
    c, owns = _acquire(config, client)
    try:
        if owns:
            c.connect(log=logger.log)
        cmd = "sacct -a -s RUNNING -P -n --format=JobID,User,AllocCPUS,Elapsed,NodeList"
        out, err, _ = c.exec_command(cmd, timeout=10)
        if err:
            logger.log(tr("cpu_cmd_error", "⚠️ sacct 命令错误: {error}").format(error=err))
            return RemoteResult(success=False, error=err, data=[], messages=list(logger.messages))
        data = _parse_sacct_cpu_data(out)
        return RemoteResult(success=True, data=data, messages=list(logger.messages))
    except Exception as exc:
        logger.log(tr("cpu_fetch_failed", "❌ 获取集群作业信息失败：{error}").format(error=exc))
        return RemoteResult(success=False, error=str(exc), data=[], messages=list(logger.messages))
    finally:
        if owns:
            c.close()


def run_squeue_detail(
    config: PipelineConfig,
    log: Optional[LogCallback] = None,
    *,
    client: Optional[SshClient] = None,
) -> RemoteResult:
    """获取远程服务器任务队列详情（squeue -o 格式）。

    Returns:
        ``data`` 字段为行列表 ``[line, ...]``，每行格式:
        ``JOBID PARTITION NAME STATE TIME NODES CPUS NODELIST``
    """
    logger = CoreLogger(callback=log)
    c, owns = _acquire(config, client)
    try:
        if owns:
            c.connect(log=logger.log)
        out, err, _ = c.exec_command(
            "squeue -o '%i %P %j %T %M %D %C %R' -h", timeout=10
        )
        if err:
            logger.log(tr("squeue_cmd_error", "⚠️ squeue 错误: {error}").format(error=err))
        lines = [ln for ln in out.splitlines() if ln.strip()]
        return RemoteResult(success=True, data=lines, messages=list(logger.messages))
    except Exception as exc:
        logger.log(tr("squeue_fetch_failed", "❌ 获取任务队列失败：{error}").format(error=exc))
        return RemoteResult(success=False, error=str(exc), data=[], messages=list(logger.messages))
    finally:
        if owns:
            c.close()


def run_server_status(
    config: PipelineConfig,
    log: Optional[LogCallback] = None,
    *,
    client: Optional[SshClient] = None,
) -> RemoteResult:
    """单次 SSH 连接同时获取集群作业、空闲资源和任务队列，减少连接开销。

    Returns:
        ``data`` 为 ``{"cpu": [[user, cpus, nodes, elapsed], ...], "idle": [...], "queue": [line, ...]}``。
    """
    logger = CoreLogger(callback=log)
    c, owns = _acquire(config, client)
    try:
        if owns:
            c.connect(log=logger.log)

        # [EN] Cluster running jobs (sacct, per-user aggregation)
        # 集群运行中作业（sacct，按用户聚合）
        sacct_out, sacct_err, _ = c.exec_command(
            "sacct -a -s RUNNING -P -n --format=JobID,User,AllocCPUS,Elapsed,NodeList",
            timeout=10,
        )
        cpu_data: list = []
        if not sacct_err:
            cpu_data = _parse_sacct_cpu_data(sacct_out)

        idle_data: list = []
        partitions: list[str] = []
        sinfo_out, sinfo_err, _ = c.exec_command(
            "sinfo -h -N -o '%N|%T|%c|%C|%P'",
            timeout=10,
        )
        if not sinfo_err:
            sinfo_data = _parse_sinfo_idle_resources(sinfo_out)
            idle_data = sinfo_data.get("idle_summary", [])
            partitions = sinfo_data.get("partitions", [])

        # 任务队列
        q_out, q_err, _ = c.exec_command(
            "squeue -o '%i %P %j %T %M %D %C %R' -h", timeout=10
        )
        queue_lines = [ln for ln in q_out.splitlines() if ln.strip()]

        return RemoteResult(
            success=True,
            data={"cpu": cpu_data, "idle": idle_data, "partitions": partitions, "queue": queue_lines},
            messages=list(logger.messages),
        )
    except Exception as exc:
        logger.log(tr("server_status_failed", "❌ 获取服务器状态失败：{error}").format(error=exc))
        return RemoteResult(
            success=False, error=str(exc), data={"cpu": [], "idle": [], "partitions": [], "queue": []}, messages=list(logger.messages)
        )
    finally:
        if owns:
            c.close()


def run_list_files(
    config: PipelineConfig,
    log: Optional[LogCallback] = None,
    *,
    client: Optional[SshClient] = None,
) -> RemoteResult:
    """列出远程工作目录下的文件详情（``ls -lh``）。

    Args:
        config: 流水线配置。
        log: 可选日志回调。

    Returns:
        ``data`` 字段为 ``ls -lh`` 原始输出文本。
    """
    logger = CoreLogger(callback=log)
    c, owns = _acquire(config, client)
    try:
        remote_dir = _resolve_remote_dir(config)
        if owns:
            c.connect(log=logger.log)
        cmd = f"ls -lh {shlex.quote(remote_dir)}"
        output, err, code = c.exec_command(cmd, log=logger.log, timeout=10)
        if code != 0:
            raise RuntimeError(err or output or tr("remote_command_exit_code", "远程命令退出码 {code}").format(code=code))
        if output:
            # [EN] Normalize line endings to avoid blank lines in log display.
            # 规范化行尾，避免日志中出现空行
            clean = output.replace("\r\n", "\n").replace("\r", "")
            logger.log(tr("remote_file_list", "📁 {path} 下的文件列表：\n{output}\n{line}").format(path=remote_dir, output=clean, line="=" * 46))
        else:
            logger.log(tr("server_directory_empty", "📂 目录为空：{path}").format(path=remote_dir))
        return RemoteResult(success=True, data=output, messages=list(logger.messages))
    except Exception as exc:
        logger.log(tr("cannot_list_remote_files", "❌ 无法列出文件：{error}").format(error=exc))
        return RemoteResult(success=False, error=str(exc), messages=list(logger.messages))
    finally:
        if owns:
            c.close()


# ── 下载 ────────────────────────────────────────────────────────────────

def run_download_results(
    config: PipelineConfig,
    log: Optional[LogCallback] = None,
    *,
    nested: bool = False,
    client: Optional[SshClient] = None,
) -> RemoteResult:
    """从远程服务器下载所有 ``ww3*.nc`` 结果文件。

    Args:
        config: 流水线配置。
        log: 可选日志回调。
        nested: 为 ``True`` 时从远程最细层 ``levelN/`` 子目录下载至本地对应目录。

    Returns:
        ``data`` 字段为已下载文件的本地路径列表。
    """
    logger = CoreLogger(callback=log)
    c, owns = _acquire(config, client)
    try:
        remote_dir = _resolve_remote_dir(config)
        local_dir = _resolve_local_dir(config)
        if owns:
            c.connect(log=logger.log)

        from workflows.infrastructure.ww3.nested_level_dirs import finest_nested_level_name

        finest = finest_nested_level_name(local_dir) if nested else None
        if nested and not finest:
            msg = tr("nested_grid_folders_not_found", "❌ 未找到 level* 网格目录，请先生成嵌套网格")
            logger.log(msg)
            return RemoteResult(success=False, error=msg, messages=list(logger.messages))

        search_dir = f"{remote_dir.rstrip('/')}/{finest}" if nested else remote_dir
        local_save = os.path.join(local_dir, finest) if nested else local_dir

        def _is_ww3_nc(name: str) -> bool:
            return name.startswith("ww3") and name.endswith(".nc")

        files = c.download_files(search_dir, local_save, _is_ww3_nc, log=logger.log)
        return RemoteResult(success=True, data=files, messages=list(logger.messages))
    except Exception as exc:
        logger.log(tr("download_results_failed", "❌ 下载结果失败：{error}").format(error=exc))
        return RemoteResult(success=False, error=str(exc), messages=list(logger.messages))
    finally:
        if owns:
            c.close()


def run_download_log(
    config: PipelineConfig,
    log: Optional[LogCallback] = None,
    *,
    client: Optional[SshClient] = None,
) -> RemoteResult:
    """从远程服务器下载运行日志 ``run.log`` 及 ``success`` / ``fail`` 标记文件。

    Args:
        config: 流水线配置。
        log: 可选日志回调。

    Returns:
        ``data`` 字段为已下载文件的本地路径列表。
    """
    logger = CoreLogger(callback=log)
    c, owns = _acquire(config, client)
    try:
        remote_dir = _resolve_remote_dir(config)
        local_dir = _resolve_local_dir(config)
        if owns:
            c.connect(log=logger.log)

        def _is_log(name: str) -> bool:
            return name in ("run.log", "success", "fail")

        files = c.download_files(remote_dir, local_dir, _is_log, log=logger.log)
        return RemoteResult(success=True, data=files, messages=list(logger.messages))
    except Exception as exc:
        logger.log(tr("download_log_failed", "❌ 下载日志失败：{error}").format(error=exc))
        return RemoteResult(success=False, error=str(exc), messages=list(logger.messages))
    finally:
        if owns:
            c.close()


# ── 清空远程（破坏性 — 需 confirmed=True）──────────────────────────────

def run_clear_remote(
    config: PipelineConfig,
    log: Optional[LogCallback] = None,
    *,
    confirmed: bool = False,
    client: Optional[SshClient] = None,
) -> RemoteResult:
    """删除远程工作目录内的全部文件（不可恢复）。

    **必须传入 ``confirmed=True``**；CLI 对应 ``--confirm``。

    Args:
        config: 流水线配置。
        log: 可选日志回调。
        confirmed: 显式确认标志。

    Returns:
        清空成功或失败对应的 ``RemoteResult``。
    """
    logger = CoreLogger(callback=log)
    if not confirmed:
        msg = (
            tr("clear_remote_blocked_confirm_required", "⚠️ 清空远程目录被阻止：这是不可恢复的操作，必须显式传入 confirmed=True（CLI: --confirm）才能执行。")
        )
        logger.log(tr("error_prefix", "❌ {message}").format(message=msg))
        return RemoteResult(success=False, error=msg, messages=list(logger.messages))

    c, owns = _acquire(config, client)
    try:
        remote_dir = _resolve_remote_dir(config)
        if owns:
            c.connect(log=logger.log)
        c.clear_remote_dir(remote_dir, log=logger.log)
        return RemoteResult(success=True, messages=list(logger.messages))
    except Exception as exc:
        logger.log(tr("clear_remote_failed", "❌ 清空失败：{error}").format(error=exc))
        return RemoteResult(success=False, error=str(exc), messages=list(logger.messages))
    finally:
        if owns:
            c.close()


# ── 取消任务 ────────────────────────────────────────────────────────────

def run_cancel_job(
    config: PipelineConfig,
    job_id: str,
    log: Optional[LogCallback] = None,
    *,
    client: Optional[SshClient] = None,
) -> RemoteResult:
    """通过 SLURM 作业 ID 取消远程任务。

    Args:
        config: 流水线配置。
        job_id: SLURM 作业 ID 字符串。
        log: 可选日志回调。

    Returns:
        取消成功或失败对应的 ``RemoteResult``。
    """
    logger = CoreLogger(callback=log)
    c, owns = _acquire(config, client)
    try:
        if owns:
            c.connect(log=logger.log)
        c.cancel_job(job_id, log=logger.log)
        return RemoteResult(success=True, messages=list(logger.messages))
    except Exception as exc:
        logger.log(tr("cancel_job_failed", "❌ 取消任务失败：{error}").format(error=exc))
        return RemoteResult(success=False, error=str(exc), messages=list(logger.messages))
    finally:
        if owns:
            c.close()
