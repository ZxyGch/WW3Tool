"""服务器操作视图模型：桥接桌面到 application.remote_ops。

各方法接受 ``PipelineConfig``，转调对应 ``run_*``，日志转发 ``on_log``，返回 ``RemoteResult``。

连接成功后持有 ``SshClient`` 实例，后续操作复用同一连接，避免重复 SSH 握手。

[EN] Server operations view model: bridges desktop to application.remote_ops.

Each method accepts ``PipelineConfig``, delegates to the corresponding ``run_*``,
forwards logs to ``on_log``, and returns ``RemoteResult``.

After successful connection, holds the ``SshClient`` instance and reuses the same
connection for subsequent operations, avoiding repeated SSH handshakes.
"""

from __future__ import annotations

from typing import Callable, Optional

from workflows.domain.config_models import PipelineConfig

LogCallback = Callable[[str], None]


class RemoteViewModel:
    # [EN] Drive SSH/SLURM remote operations use cases.
    """驱动 SSH/SLURM 远程运维用例。"""

    def __init__(self, *, on_log: Optional[LogCallback] = None) -> None:
        self._on_log = on_log
        self._client = None  # [EN] Persistent SSH client
        # 持久化 SSH 客户端

    def _log(self, message: str) -> None:
        if self._on_log is not None:
            self._on_log(str(message))

    @property
    def is_connected(self) -> bool:
        return self._client is not None and self._client.is_alive()

    def close(self) -> None:
        # [EN] Close persistent connection.
        """关闭持久化连接。"""
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None

    def _ensure_client(self, config: PipelineConfig):
        # [EN] Ensure an available connection: auto-reconnect when disconnected.
        """确保有可用连接：断开时自动重连。"""
        if self._client is not None and self._client.is_alive():
            return self._client
        from workflows.infrastructure.remote.ssh_client import SshClient
        self._client = SshClient(config.server)
        self._client.connect(log=self._log)
        return self._client

    def connect_test(self, config: PipelineConfig):
        from workflows.infrastructure.remote.ssh_client import SshClient
        from workflows.support.logging import CoreLogger

        logger = CoreLogger(callback=self._log)
        client = SshClient(config.server)
        try:
            client.connect(log=logger.log)
            out, _, _ = client.exec_command("hostname && uname -r && uptime", log=logger.log)
            for line in out.splitlines():
                logger.log(line)
            # [EN] Connection successful, keep as persistent client
            # 连接成功，保留为持久化 client
            self._client = client
            from workflows.application.remote_ops import RemoteResult
            return RemoteResult(success=True, messages=list(logger.messages))
        except Exception as exc:
            client.close()
            self._client = None
            from workflows.application.remote_ops import RemoteResult
            return RemoteResult(success=False, error=str(exc), messages=list(logger.messages))

    def queue_status(self, config: PipelineConfig):
        from workflows.application.remote_ops import run_queue_status

        return run_queue_status(config, log=self._log, client=self._ensure_client(config))

    def cpu_ranking(self, config: PipelineConfig):
        from workflows.application.remote_ops import run_cpu_ranking

        return run_cpu_ranking(config, log=self._log, client=self._ensure_client(config))

    def squeue_detail(self, config: PipelineConfig):
        from workflows.application.remote_ops import run_squeue_detail

        return run_squeue_detail(config, log=self._log, client=self._ensure_client(config))

    def server_status(self, config: PipelineConfig):
        from workflows.application.remote_ops import run_server_status

        return run_server_status(config, log=self._log, client=self._ensure_client(config))

    def list_files(self, config: PipelineConfig):
        from workflows.application.remote_ops import run_list_files

        return run_list_files(config, log=self._log, client=self._ensure_client(config))

    def cancel_job(self, config: PipelineConfig, job_id: str):
        from workflows.application.remote_ops import run_cancel_job

        return run_cancel_job(config, job_id, log=self._log, client=self._ensure_client(config))

    def upload(self, config: PipelineConfig, *, confirmed: bool = True):
        from workflows.application.remote_ops import run_upload

        return run_upload(config, log=self._log, confirmed=confirmed, client=self._ensure_client(config))

    def upload_without_forcing(self, config: PipelineConfig, *, confirmed: bool = True):
        from workflows.application.remote_ops import run_upload_without_forcing

        return run_upload_without_forcing(config, log=self._log, confirmed=confirmed, client=self._ensure_client(config))

    def slurm_idle_resources(self, config: PipelineConfig):
        from workflows.application.remote_ops import run_slurm_idle_resources

        return run_slurm_idle_resources(config, log=self._log, client=self._ensure_client(config))

    def submit(self, config: PipelineConfig, *, script: str = "server.sh"):
        from workflows.application.remote_ops import run_submit

        return run_submit(config, log=self._log, script=script, client=self._ensure_client(config))

    def check_status(self, config: PipelineConfig):
        from workflows.application.remote_ops import run_check_status

        return run_check_status(config, log=self._log, client=self._ensure_client(config))

    def inject_ntfy_listener(self, config: PipelineConfig):
        from workflows.application.remote_ops import run_inject_ntfy_listener

        return run_inject_ntfy_listener(config, log=self._log, client=self._ensure_client(config))

    def clear_remote(self, config: PipelineConfig, *, confirmed: bool = True):
        from workflows.application.remote_ops import run_clear_remote

        return run_clear_remote(config, log=self._log, confirmed=confirmed, client=self._ensure_client(config))

    def download_results(self, config: PipelineConfig, *, nested: bool = False):
        from workflows.application.remote_ops import run_download_results

        return run_download_results(config, log=self._log, nested=nested, client=self._ensure_client(config))

    def download_log(self, config: PipelineConfig):
        from workflows.application.remote_ops import run_download_log

        return run_download_log(config, log=self._log, client=self._ensure_client(config))

    def exec_command(self, config: PipelineConfig, command: str):
        # [EN] Execute arbitrary command on remote server and log output.
        """在远程服务器执行任意命令并将输出记录到日志。"""
        from workflows.application.remote_ops import RemoteResult

        client = self._ensure_client(config)
        self._log(f"$ {command}")
        try:
            out, err, code = client.exec_command(command, log=self._log, timeout=60)
            if out:
                for line in out.splitlines():
                    self._log(line)
            if err:
                for line in err.splitlines():
                    self._log(f"[stderr] {line}")
            if code != 0:
                self._log(f"[exit code: {code}]")
            return RemoteResult(success=(code == 0), messages=[])
        except Exception as exc:
            self._log(f"❌ {exc}")
            return RemoteResult(success=False, error=str(exc), messages=[])
