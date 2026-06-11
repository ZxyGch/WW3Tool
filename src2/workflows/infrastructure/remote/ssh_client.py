"""纯 SSH/SFTP 客户端 — 无 Qt、无线程、无信号。

所有方法均为*同步*调用，通过 ``log`` 回调输出进度。
桌面层在自有线程中包装；CLI 直接调用。
"""

from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path
from typing import Callable, Iterator, List, Optional, Tuple

from ...domain.config_models import ServerConfig
from ...support.translations import tr

LogFn = Callable[[str], None]
_noop: LogFn = lambda _: None


def _make_ssh():
    """延迟导入 paramiko；未安装时抛出带安装提示的 RuntimeError。"""
    try:
        import paramiko
        return paramiko
    except ImportError as exc:
        raise RuntimeError(
            "SSH 功能需要 paramiko，请先安装：pip install paramiko"
        ) from exc


class SshClient:
    """基于 paramiko 的 SSH/SFTP 薄封装。

    典型用法::

        client = SshClient(config)
        client.connect(log=print)          # 失败则抛 ConnectionError
        client.upload_folder(local, remote, log=print)
        client.exec_script("server.sh", remote_dir, log=print)
        client.close()
    """

    def __init__(self, config: ServerConfig) -> None:
        """保存 ``ServerConfig``；连接在 ``connect()`` 时建立。"""
        self._config = config
        self._ssh = None
        self._conn_args: Optional[Tuple[str, int, str, str]] = None

    # ── connection ────────────────────────────────────────────────────────────

    def connect(self, *, log: LogFn = _noop, timeout: int = 15) -> None:
        """建立 SSH 连接；失败时抛出 ``ConnectionError``。"""
        paramiko = _make_ssh()
        cfg = self._config
        if not cfg.host or not cfg.user:
            raise ConnectionError(
                tr("step5_config_missing_host_user", "❌ 请先在 params.yml server: 中配置 host 和 user")
            )
        log(tr("step5_connecting_server", "🔄 正在连接服务器 {host}:{port}...").format(
            host=cfg.host, port=cfg.port))
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        kwargs: dict = dict(
            hostname=cfg.host,
            port=cfg.port,
            username=cfg.user,
            timeout=timeout,
            look_for_keys=bool(cfg.key_file),
            allow_agent=bool(cfg.key_file),
        )
        if cfg.key_file and Path(str(cfg.key_file)).is_file():
            kwargs["key_filename"] = str(cfg.key_file)
        elif cfg.password:
            kwargs["password"] = cfg.password
            kwargs["look_for_keys"] = False
            kwargs["allow_agent"] = False
        try:
            ssh.connect(**kwargs)
        except Exception as exc:
            raise ConnectionError(
                tr("step5_connect_failed", "❌ 连接服务器失败：{error}").format(error=exc)
            ) from exc
        self._ssh = ssh
        self._conn_args = (cfg.host, cfg.port, cfg.user, cfg.password)
        log(tr("connect_success_log", "✅ 连接服务器成功"))

    def is_alive(self) -> bool:
        """当前 SSH 传输层是否仍处于活动状态。"""
        if self._ssh is None:
            return False
        transport = self._ssh.get_transport()
        return transport is not None and transport.is_active()

    def ensure_connected(self, *, log: LogFn = _noop) -> None:
        """若连接已断开则自动重连。"""
        if not self.is_alive():
            log("⚠️ SSH 连接已断开，尝试重新连接...")
            self.connect(log=log)

    def close(self) -> None:
        """关闭 SSH 连接并释放底层 socket。"""
        if self._ssh is not None:
            try:
                self._ssh.close()
            except Exception:
                pass
            self._ssh = None

    # ── remote execution ──────────────────────────────────────────────────────

    def exec_script(
        self,
        script_name: str,
        remote_dir: str,
        *,
        log: LogFn = _noop,
    ) -> int:
        """在远程主机执行 shell 脚本并流式输出日志。

        返回进程退出码。
        """
        self.ensure_connected(log=log)
        cmd = (
            f"cd '{remote_dir}' && chmod +x {script_name} 2>/dev/null || true; "
            f"cd '{remote_dir}' && bash {script_name}"
        )
        log(f"▶ {cmd}")
        stdin, stdout, stderr = self._ssh.exec_command(cmd, get_pty=True)
        for line in iter(stdout.readline, ""):
            if not line:
                break
            log(line.rstrip())
        err = stderr.read().decode("utf-8", errors="ignore").strip()
        if err:
            for line in err.splitlines():
                log(line)
        code = stdout.channel.recv_exit_status()
        if code == 0:
            log(tr("remote_script_completed", "✅ 远程脚本执行完成"))
        else:
            log(tr("remote_script_exit_code", "❌ 远程脚本返回码: {code}").format(code=code))
        return code

    def exec_command(self, cmd: str, *, log: LogFn = _noop, timeout: int = 30) -> Tuple[str, str, int]:
        """执行任意远程命令，返回 ``(stdout, stderr, exit_code)``。"""
        self.ensure_connected(log=log)
        stdin, stdout, stderr = self._ssh.exec_command(cmd, get_pty=True, timeout=timeout)
        out = stdout.read().decode("utf-8", errors="ignore").strip()
        err = stderr.read().decode("utf-8", errors="ignore").strip()
        code = stdout.channel.recv_exit_status()
        return out, err, code

    # ── SFTP helpers ──────────────────────────────────────────────────────────

    def _sftp(self):
        self.ensure_connected()
        return self._ssh.open_sftp()

    def list_files(self, remote_dir: str) -> List[str]:
        """列出远程目录下的文件名。"""
        sftp = self._sftp()
        try:
            return sftp.listdir(remote_dir)
        finally:
            sftp.close()

    def _ensure_remote_dir(self, sftp, remote_dir: str) -> None:
        parts = remote_dir.strip("/").split("/")
        cur = ""
        for p in parts:
            cur += "/" + p
            try:
                sftp.stat(cur)
            except IOError:
                sftp.mkdir(cur)

    # ── upload ────────────────────────────────────────────────────────────────

    # Files that must have \r stripped before upload (Windows-edited shell scripts)
    _UNIX_EOL_FILES = frozenset({"server.sh", "local.sh", "export.sh", "ww3.slurm"})

    def upload_folder(
        self,
        local_dir: str,
        remote_dir: str,
        *,
        log: LogFn = _noop,
    ) -> None:
        """通过 SFTP 递归上传本地目录到 ``remote_dir``。

        上传前会将 ``server.sh`` 等脚本规范为 LF 换行。
        """
        self.ensure_connected(log=log)
        sftp = self._sftp()
        try:
            if remote_dir.startswith("~"):
                remote_dir = remote_dir.replace("~", f"/home/{self._config.user}", 1)
            log(tr("upload_folder_start", "📤 开始上传文件夹到 {path} ...").format(path=remote_dir))
            self._ensure_remote_dir(sftp, remote_dir)

            total_files = sum(len(fs) for _, _, fs in os.walk(local_dir))
            uploaded = 0

            for root, dirs, files in os.walk(local_dir):
                rel = os.path.relpath(root, local_dir)
                remote_path = os.path.join(remote_dir, rel).replace("\\", "/")
                try:
                    self._ensure_remote_dir(sftp, remote_path)
                except Exception as exc:
                    log(f"⚠️ 无法创建远程目录 {remote_path}: {exc}")
                    continue

                for fname in files:
                    local_file = os.path.join(root, fname)
                    remote_file = os.path.join(remote_path, fname).replace("\\", "/")
                    try:
                        if fname in self._UNIX_EOL_FILES:
                            with open(local_file, "rb") as fh:
                                content = fh.read()
                            if b"\r" in content:
                                content = content.replace(b"\r", b"")
                                with tempfile.NamedTemporaryFile(delete=False, suffix=fname) as tmp:
                                    tmp.write(content)
                                    tmp_path = tmp.name
                                try:
                                    sftp.put(tmp_path, remote_file)
                                finally:
                                    os.unlink(tmp_path)
                            else:
                                sftp.put(local_file, remote_file)
                        else:
                            sftp.put(local_file, remote_file)
                        uploaded += 1
                        log(f"  ↑ {os.path.join(rel, fname).replace(os.sep, '/')}  [{uploaded}/{total_files}]")
                    except Exception as exc:
                        log(f"❌ 上传 {fname} 失败: {exc}")
        finally:
            sftp.close()
        log(f"✅ 上传完成，共 {uploaded} 个文件 → {remote_dir}")

    # ── download ──────────────────────────────────────────────────────────────

    def download_files(
        self,
        remote_dir: str,
        local_dir: str,
        pattern_fn: Callable[[str], bool],
        *,
        log: LogFn = _noop,
    ) -> List[str]:
        """下载 ``remote_dir`` 中满足 ``pattern_fn`` 的文件到 ``local_dir``。

        返回已成功下载的本地绝对路径列表。
        """
        self.ensure_connected(log=log)
        sftp = self._sftp()
        downloaded: List[str] = []
        try:
            try:
                all_files = sftp.listdir(remote_dir)
            except IOError as exc:
                raise RuntimeError(f"无法列出远程目录 {remote_dir}: {exc}") from exc

            matched = [f for f in all_files if pattern_fn(f)]
            if not matched:
                log("⚠️ 远程目录未找到匹配的文件")
                return downloaded

            os.makedirs(local_dir, exist_ok=True)
            for fname in matched:
                rpath = f"{remote_dir.rstrip('/')}/{fname}"
                lpath = os.path.join(local_dir, fname)
                try:
                    size = sftp.stat(rpath).st_size or 0
                    log(f"⬇ {fname}  ({size / 1024:.1f} KB)")
                    last_pct = [0]

                    def _progress(transferred: int, total: int = size, name: str = fname) -> None:
                        pct = int(transferred / total * 100) if total else 0
                        if pct > last_pct[0]:
                            last_pct[0] = pct
                            log(f"  {name} ... {pct}%")

                    sftp.get(rpath, lpath, callback=_progress)
                    downloaded.append(lpath)
                    log(f"  ✅ {fname} 下载完成")
                except Exception as exc:
                    log(f"❌ 下载 {fname} 失败: {exc}")
        finally:
            sftp.close()
        return downloaded

    # ── status checks ─────────────────────────────────────────────────────────

    def check_completion(self, remote_dir: str, *, log: LogFn = _noop) -> str:
        """根据远程目录中的 ``success.log`` / ``fail.log`` 判断任务状态。

        返回 ``success``、``failed`` 或 ``running``。
        """
        self.ensure_connected(log=log)
        sftp = self._sftp()
        try:
            files = sftp.listdir(remote_dir)
        except IOError as exc:
            raise RuntimeError(f"无法访问远程目录 {remote_dir}: {exc}") from exc
        finally:
            sftp.close()
        if "success.log" in files:
            return "success"
        if "fail.log" in files:
            return "failed"
        return "running"

    def queue_status(self, *, log: LogFn = _noop) -> str:
        """执行 ``squeue -l`` 并返回标准输出文本。"""
        out, err, _ = self.exec_command("squeue -l", log=log, timeout=10)
        if err:
            log(f"⚠️ squeue 错误: {err}")
        return out

    def cancel_job(self, job_id: str, *, log: LogFn = _noop) -> None:
        """通过 ``scancel`` 取消指定 SLURM 任务。"""
        out, err, code = self.exec_command(f"scancel {job_id}", log=log)
        if code == 0:
            log(f"✅ 已取消任务 {job_id}")
        else:
            log(f"❌ 取消任务 {job_id} 失败: {err or out}")

    def clear_remote_dir(self, remote_dir: str, *, log: LogFn = _noop) -> None:
        """清空 ``remote_dir`` 内所有文件与子目录（保留目录本身）。"""
        cmd = f"cd '{remote_dir}' && sh -c 'rm -rf * .[!.]*' 2>&1 || true"
        log(f"🗑 清空远程目录: {remote_dir}")
        out, err, code = self.exec_command(cmd, log=log, timeout=60)
        if code == 0 or "No such file" not in err:
            log(f"✅ 已清空 {remote_dir}")
        else:
            log(f"⚠️ 清空时有警告: {err}")
