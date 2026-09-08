"""模拟断线、部分成功与大小不符，验证传输结果和目标文件完整性。"""

import posixpath
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from workflows.application.remote_ops import run_upload, run_download_results, run_download_log
from workflows.domain.config_models import PipelineConfig, WorkdirConfig
from workflows.infrastructure.remote.ssh_client import SshClient, TransferError
from workflows.interfaces.command_line import _remote
from workflows.interfaces.json_output import capture


class MemorySftp:
    """在内存中模拟 SFTP，所有本地写入限定于测试临时目录。"""

    def __init__(self):
        self.files = {}
        self.upload_fail = set()
        self.download_fail = set()
        self.truncate_download = False
        self.truncate_upload = False
        self.replace_supported = True
        self.mkdir_failure = None

    def close(self):
        pass

    def stat(self, path):
        if self.mkdir_failure == path:
            raise FileNotFoundError(path)
        return SimpleNamespace(st_size=len(self.files.get(path, b"")))

    def mkdir(self, path):
        if self.mkdir_failure == path:
            raise PermissionError(path)

    def listdir(self, path):
        return [posixpath.basename(name) for name in sorted(self.files)
                if posixpath.dirname(name) == path]

    def put(self, source, target, *, confirm):
        assert confirm
        name = Path(source).name
        content = Path(source).read_bytes()
        if name in self.upload_fail:
            self.files[target] = content[:2]
            raise OSError("模拟上传中断")
        self.files[target] = content[:-1] if self.truncate_upload else content

    def get(self, source, target, *, callback):
        content = self.files[source]
        if posixpath.basename(source) in self.download_fail:
            Path(target).write_bytes(content[:2])
            raise OSError("模拟下载中断")
        Path(target).write_bytes(content[:-1] if self.truncate_download else content)
        callback(len(content), len(content))

    def posix_rename(self, source, target):
        if not self.replace_supported:
            raise OSError("Operation unsupported")
        self.files[target] = self.files.pop(source)

    def rename(self, source, target):
        if target in self.files:
            raise FileExistsError(target)
        self.files[target] = self.files.pop(source)

    def remove(self, path):
        if path not in self.files:
            raise FileNotFoundError(path)
        del self.files[path]


@pytest.fixture
def transfer(tmp_path):
    config = PipelineConfig(source_path=None, base_dir=tmp_path, workdir=WorkdirConfig(tmp_path))
    config.server.remote_dir = "/synthetic/job"
    sftp = MemorySftp()
    client = SshClient(config.server)
    client.ensure_connected = Mock()
    client._sftp = lambda: sftp
    return config, client, sftp


@pytest.mark.parametrize("partial", [False, True])
def test_upload_failure_is_reported_with_completed_and_failed_files(transfer, partial):
    config, client, sftp = transfer
    (config.workdir.path / "wind.nc").write_bytes(b"new complete wind")
    sftp.files["/synthetic/job/wind.nc"] = b"existing complete wind"
    sftp.upload_fail.add("wind.nc")
    if partial:
        (config.workdir.path / "grid.bot").write_bytes(b"grid")
    result = run_upload(config, confirmed=True, client=client)
    assert not result.success
    assert "/synthetic/job/wind.nc" in result.data["failed"]
    assert len(result.data["completed"]) == int(partial)
    assert sftp.files["/synthetic/job/wind.nc"] == b"existing complete wind"
    assert not any(name.endswith(".part") for name in sftp.files)
    with capture("upload") as json_result:
        assert _remote(lambda: result) != 0
    payload = json_result.to_dict()
    assert payload["status"] == "error"
    assert payload["data"]["remote_result"]["failed"] == result.data["failed"]
    assert "/synthetic/job/wind.nc" in payload["error"]["message"]


def test_upload_directory_failure_is_not_success(transfer):
    config, client, sftp = transfer
    sub = config.workdir.path / "level1"
    sub.mkdir()
    (sub / "grid.bot").write_bytes(b"grid")
    sftp.mkdir_failure = "/synthetic/job/level1"
    result = run_upload(config, confirmed=True, client=client)
    assert not result.success
    assert "level1" in result.data["failed"]


def test_successful_upload_is_complete_and_normalizes_shell_newlines(transfer):
    config, client, sftp = transfer
    path = config.workdir.path / "server.sh"
    path.write_bytes(b"#!/bin/bash\r\necho ready\r\n")
    sftp.files["/synthetic/job/server.sh"] = b"existing script"
    result = run_upload(config, confirmed=True, client=client)
    assert result.success
    assert sftp.files["/synthetic/job/server.sh"] == b"#!/bin/bash\necho ready\n"
    assert path.read_bytes().endswith(b"\r\n")


def test_upload_size_mismatch_preserves_destination(transfer):
    config, client, sftp = transfer
    (config.workdir.path / "wind.nc").write_bytes(b"complete")
    sftp.files["/synthetic/job/wind.nc"] = b"existing"
    sftp.truncate_upload = True
    assert not run_upload(config, confirmed=True, client=client).success
    assert sftp.files["/synthetic/job/wind.nc"] == b"existing"


def test_server_without_atomic_replace_preserves_existing_target(transfer):
    config, client, sftp = transfer
    (config.workdir.path / "wind.nc").write_bytes(b"complete")
    sftp.replace_supported = False
    assert run_upload(config, confirmed=True, client=client).success
    sftp.files["/synthetic/job/wind.nc"] = b"existing"
    assert not run_upload(config, confirmed=True, client=client).success
    assert sftp.files["/synthetic/job/wind.nc"] == b"existing"


def test_matching_upload_propagates_partial_failure(transfer):
    config, client, sftp = transfer
    for name in ("grid.bot", "wind.nc", "ignored.nc"):
        (config.workdir.path / name).write_bytes(b"content")
    sftp.upload_fail.add("wind.nc")
    with pytest.raises(TransferError) as failure:
        client.upload_matching_files(str(config.workdir.path), config.server.remote_dir,
                                     lambda name: name != "ignored.nc", recursive=True)
    assert failure.value.details["completed"] == ["/synthetic/job/grid.bot"]
    assert "/synthetic/job/ignored.nc" not in sftp.files


@pytest.mark.parametrize("partial", [False, True])
def test_download_failure_preserves_existing_file_and_reports_failure(transfer, partial):
    config, client, sftp = transfer
    target = config.workdir.path / "ww3.2020.nc"
    target.write_bytes(b"existing complete result")
    sftp.files["/synthetic/job/ww3.2020.nc"] = b"new complete result"
    sftp.download_fail.add("ww3.2020.nc")
    if partial:
        sftp.files["/synthetic/job/ww3.2021.nc"] = b"complete next result"
    result = run_download_results(config, client=client)
    assert not result.success
    assert len(result.data["completed"]) == int(partial)
    assert "/synthetic/job/ww3.2020.nc" in result.data["failed"]
    assert target.read_bytes() == b"existing complete result"
    assert not list(config.workdir.path.glob("*.part"))


@pytest.mark.parametrize("truncated", [False, True])
def test_download_size_validation_and_successful_replace(transfer, truncated):
    config, client, sftp = transfer
    target = config.workdir.path / "ww3.2020.nc"
    target.write_bytes(b"existing")
    sftp.files["/synthetic/job/ww3.2020.nc"] = b"complete result"
    sftp.truncate_download = truncated
    result = run_download_results(config, client=client)
    assert result.success == (not truncated)
    assert target.read_bytes() == (b"existing" if truncated else b"complete result")


def test_no_matching_results_is_not_success(transfer):
    config, client, _ = transfer
    assert not run_download_results(config, client=client).success


def test_log_download_also_propagates_transfer_failure(transfer):
    config, client, sftp = transfer
    sftp.files["/synthetic/job/run.log"] = b"complete log"
    sftp.download_fail.add("run.log")
    result = run_download_log(config, client=client)
    assert not result.success
    assert "/synthetic/job/run.log" in result.data["failed"]
