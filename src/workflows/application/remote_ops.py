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
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from ..domain.config_models import PipelineConfig
from ..infrastructure.remote.ssh_client import SshClient
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
    """
    remote_dir = config.server.remote_dir.strip()
    if not remote_dir:
        base = config.server.default_remote_dir.strip()
        if not base:
            raise ValueError(
                tr("remote_dir_missing", "❌ server.remote_dir 和 server.default_remote_dir 均未配置。请在 params.yml 的 server: 段填写远程工作目录。")
            )
        workdir_name = config.workdir.path.name if config.workdir.path else ""
        if workdir_name:
            tail = os.path.basename(base.rstrip("/"))
            remote_dir = base.rstrip("/") if tail == workdir_name else base.rstrip("/") + "/" + workdir_name
        else:
            remote_dir = base
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


# ── 提交作业 ────────────────────────────────────────────────────────────

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
    """检查远程作业是否已完成（检测 ``success.log`` / ``fail.log``）。

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
            "success": tr("remote_status_success", "✅ 检测到 success.log，计算已完成"),
            "failed": tr("remote_status_failed", "❌ 检测到 fail.log，计算失败"),
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


def run_cpu_ranking(
    config: PipelineConfig,
    log: Optional[LogCallback] = None,
    *,
    client: Optional[SshClient] = None,
) -> RemoteResult:
    """获取远程服务器 CPU 占用排行（top 5 进程）。

    Returns:
        ``data`` 字段为 ``[[pid, user, cpu%], ...]`` 列表。
    """
    logger = CoreLogger(callback=log)
    c, owns = _acquire(config, client)
    try:
        if owns:
            c.connect(log=logger.log)
        out, err, _ = c.exec_command(
            "ps -eo pid,user,pcpu --sort=-pcpu | head -n 6", timeout=10
        )
        if err:
            logger.log(tr("cpu_cmd_error", "⚠️ CPU 命令错误: {error}").format(error=err))
            return RemoteResult(success=False, error=err, data=[], messages=list(logger.messages))
        lines = [ln for ln in out.splitlines() if ln.strip()]
        # 去掉表头
        data = []
        for line in lines[1:]:
            parts = line.split()
            if len(parts) >= 3:
                data.append([parts[0], parts[1], parts[2]])
        return RemoteResult(success=True, data=data, messages=list(logger.messages))
    except Exception as exc:
        logger.log(tr("cpu_fetch_failed", "❌ 获取 CPU 排行失败：{error}").format(error=exc))
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
        ``JOBID PARTITION NAME STATE TIME NODES NODELIST``
    """
    logger = CoreLogger(callback=log)
    c, owns = _acquire(config, client)
    try:
        if owns:
            c.connect(log=logger.log)
        out, err, _ = c.exec_command(
            "squeue -o '%i %P %j %T %M %D %R' -h", timeout=10
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
    """单次 SSH 连接同时获取 CPU 排行和任务队列，减少连接开销。

    Returns:
        ``data`` 为 ``{"cpu": [[pid, user, cpu%], ...], "queue": [line, ...]}``。
    """
    logger = CoreLogger(callback=log)
    c, owns = _acquire(config, client)
    try:
        if owns:
            c.connect(log=logger.log)

        # CPU 排行
        cpu_out, cpu_err, _ = c.exec_command(
            "ps -eo pid,user,pcpu --sort=-pcpu | head -n 6", timeout=10
        )
        cpu_data: list = []
        if not cpu_err:
            for line in cpu_out.splitlines()[1:]:
                parts = line.split()
                if len(parts) >= 3:
                    cpu_data.append([parts[0], parts[1], parts[2]])

        # 任务队列
        q_out, q_err, _ = c.exec_command(
            "squeue -o '%i %P %j %T %M %D %R' -h", timeout=10
        )
        queue_lines = [ln for ln in q_out.splitlines() if ln.strip()]

        return RemoteResult(
            success=True,
            data={"cpu": cpu_data, "queue": queue_lines},
            messages=list(logger.messages),
        )
    except Exception as exc:
        logger.log(tr("server_status_failed", "❌ 获取服务器状态失败：{error}").format(error=exc))
        return RemoteResult(
            success=False, error=str(exc), data={"cpu": [], "queue": []}, messages=list(logger.messages)
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
            logger.log(tr("remote_file_list", "📁 {path} 下的文件列表：\n{output}\n{line}").format(path=remote_dir, output=output, line="=" * 46))
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
        nested: 为 ``True`` 时从远程 ``fine/`` 子目录下载至本地 ``fine/``。

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

        search_dir = f"{remote_dir.rstrip('/')}/fine" if nested else remote_dir
        local_save = os.path.join(local_dir, "fine") if nested else local_dir

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
    """从远程服务器下载 ``success.log`` 和/或 ``fail.log``。

    Args:
        config: 流水线配置。
        log: 可选日志回调。

    Returns:
        ``data`` 字段为已下载日志文件的本地路径列表。
    """
    logger = CoreLogger(callback=log)
    c, owns = _acquire(config, client)
    try:
        remote_dir = _resolve_remote_dir(config)
        local_dir = _resolve_local_dir(config)
        if owns:
            c.connect(log=logger.log)

        def _is_log(name: str) -> bool:
            return name in ("success.log", "fail.log")

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