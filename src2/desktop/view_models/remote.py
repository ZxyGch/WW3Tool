"""服务器操作视图模型：桥接桌面到 application.remote_ops。

各方法接受 ``PipelineConfig``，转调对应 ``run_*``，日志转发 ``on_log``，返回 ``RemoteResult``。
"""

from __future__ import annotations

from typing import Callable, Optional

from workflows.domain.config_models import PipelineConfig

LogCallback = Callable[[str], None]


class RemoteViewModel:
    """驱动 SSH/SLURM 远程运维用例。"""

    def __init__(self, *, on_log: Optional[LogCallback] = None) -> None:
        self._on_log = on_log

    def _log(self, message: str) -> None:
        if self._on_log is not None:
            self._on_log(str(message))

    def connect_test(self, config: PipelineConfig):
        from workflows.application.remote_ops import run_connect_test

        return run_connect_test(config, log=self._log)

    def queue_status(self, config: PipelineConfig):
        from workflows.application.remote_ops import run_queue_status

        return run_queue_status(config, log=self._log)

    def list_files(self, config: PipelineConfig):
        from workflows.application.remote_ops import run_list_files

        return run_list_files(config, log=self._log)

    def cancel_job(self, config: PipelineConfig, job_id: str):
        from workflows.application.remote_ops import run_cancel_job

        return run_cancel_job(config, job_id, log=self._log)

    def upload(self, config: PipelineConfig, *, confirmed: bool = True):
        from workflows.application.remote_ops import run_upload

        return run_upload(config, log=self._log, confirmed=confirmed)

    def submit(self, config: PipelineConfig, *, script: str = "server.sh"):
        from workflows.application.remote_ops import run_submit

        return run_submit(config, log=self._log, script=script)

    def check_status(self, config: PipelineConfig):
        from workflows.application.remote_ops import run_check_status

        return run_check_status(config, log=self._log)

    def clear_remote(self, config: PipelineConfig, *, confirmed: bool = True):
        from workflows.application.remote_ops import run_clear_remote

        return run_clear_remote(config, log=self._log, confirmed=confirmed)

    def download_results(self, config: PipelineConfig, *, nested: bool = False):
        from workflows.application.remote_ops import run_download_results

        return run_download_results(config, log=self._log, nested=nested)

    def download_log(self, config: PipelineConfig):
        from workflows.application.remote_ops import run_download_log

        return run_download_log(config, log=self._log)
