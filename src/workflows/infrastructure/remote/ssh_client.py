"""纯 SSH/SFTP 客户端 — 无 Qt、无线程、无信号。

所有方法均为*同步*调用，通过 ``log`` 回调输出进度。
桌面层在自有线程中包装；CLI 直接调用。

[EN] Pure SSH/SFTP client — no Qt, no threads, no signals.

All methods are *synchronous* calls, reporting progress via a ``log`` callback.
The desktop layer wraps calls in its own thread; CLI calls directly.
"""

from __future__ import annotations

import contextlib
import os
import posixpath
import shlex
import stat
import sys
import tempfile
import time
from pathlib import Path
from typing import Callable, Iterator, List, Optional, Tuple

from ...domain.config_models import ServerConfig
from ...support.formatting import format_file_size
from ...support.translations import tr
from .ssh_config import resolve_server_connection

LogFn = Callable[[str], None]
_noop: LogFn = lambda _: None

# [EN] Substrings in exception messages that indicate a transient network-level
# failure worth retrying (SSH banner not received, socket timeout, EOF during
# handshake, connection reset).
# 瞬态网络错误关键词，匹配时自动重试。
# [EN] Keywords for transient network errors; matched automatically for retry.
_TRANSIENT_ERROR_MARKERS = (
    "error reading ssh protocol banner",
    "banner",
    "eof",
    "timed out",
    "timeout",
    "connection reset",
    "connection refused",
    "no route to host",
    "socket is closed",
)

def _is_transient_error(exc: Exception) -> bool:
    """判断异常是否为可重试的瞬态网络错误。

    [EN] Return ``True`` when the exception looks like a transient network
    issue (SSH banner missing, EOF, timeout, reset) that may succeed on retry.
    """
    msg = str(exc).lower()
    return any(marker in msg for marker in _TRANSIENT_ERROR_MARKERS)


def _connect_error_hint(exc: Optional[Exception], ssh_config_host: str = "") -> str:
    """根据异常类型返回常见原因提示（附加到错误消息末尾）。

    [EN] Return a hint string with common causes based on the exception type.
    """
    if exc is None:
        return ""
    msg = str(exc).lower()
    hints: list[str] = []
    if "banner" in msg or "eof" in msg:
        hints.append(tr(
            "connect_hint_banner",
            "可能原因：SSH 服务未启动或过载、防火墙拦截、端口错误",
        ))
    elif "timed out" in msg or "timeout" in msg:
        hints.append(tr(
            "connect_hint_timeout",
            "可能原因：服务器不可达、网络中断、防火墙阻止、IP/端口错误",
        ))
    elif "connection refused" in msg:
        hints.append(tr(
            "connect_hint_refused",
            "可能原因：SSH 服务未启动、端口错误（默认 22）",
        ))
    elif "authentication" in msg or "auth" in msg:
        hints.append(tr(
            "connect_hint_auth",
            "可能原因：用户名/密码错误、密钥文件无效或权限不正确",
        ))
    elif "no route" in msg or "network" in msg:
        hints.append(tr(
            "connect_hint_network",
            "可能原因：网络不可达、VPN 未连接、IP 地址错误",
        ))
    if not hints:
        return ""
    return "\n  💡 " + hints[0]


def _make_ssh():
    """延迟导入 paramiko；未安装时抛出带安装提示的 RuntimeError。

    同时将 paramiko 的日志级别设为 CRITICAL，屏蔽其内部 traceback 输出。

    [EN] Lazy-import paramiko; raises a RuntimeError with installation
    instructions if not installed. Also sets paramiko's log level to
    CRITICAL to suppress its internal traceback output.
    """
    try:
        import logging
        import paramiko
        # [EN] Suppress paramiko's internal traceback (e.g. "Exception (client):
        # Error reading SSH protocol banner") — we handle errors ourselves.
        # 屏蔽 paramiko 内部的 traceback 输出，由我们统一处理错误信息。
        for name in ("paramiko", "paramiko.transport"):
            logging.getLogger(name).setLevel(logging.CRITICAL)
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

    [EN] Thin wrapper around paramiko for SSH/SFTP.

    Typical usage::

        client = SshClient(config)
        client.connect(log=print)          # raises ConnectionError on failure
        client.upload_folder(local, remote, log=print)
        client.exec_script("server.sh", remote_dir, log=print)
        client.close()
    """

    def __init__(self, config: ServerConfig) -> None:
        """保存 ``ServerConfig``；连接在 ``connect()`` 时建立。

        [EN] Store ``ServerConfig``; the connection is established when ``connect()`` is called.
        """
        self._config = config
        self._ssh = None
        self._conn_args: Optional[Tuple[str, int, str, str]] = None

    # ── connection ────────────────────────────────────────────────────────────

    def connect(self, *, log: LogFn = _noop, timeout: int = 15, retries: int = 3) -> None:
        """建立 SSH 连接；失败时抛出 ``ConnectionError``。

        对瞬态网络错误（banner 缺失、EOF、超时、连接重置）自动重试，
        最多 ``retries`` 次，间隔递增（2s, 4s, 6s...）。

        [EN] Establish an SSH connection; raises ``ConnectionError`` on failure.
        Automatically retries transient network errors (banner missing, EOF,
        timeout, reset) up to ``retries`` times with increasing delay.
        """
        paramiko = _make_ssh()
        cfg = self._config
        conn = resolve_server_connection(cfg)
        if cfg.ssh_config_host:
            log(tr(
                "step5_connecting_ssh_config",
                "🔄 正在通过 SSH 配置 [{alias}] 连接 {host}:{port}...",
            ).format(alias=cfg.ssh_config_host, host=conn.host, port=conn.port))
        elif not conn.host or not conn.user:
            raise ConnectionError(
                tr("step5_config_missing_host_user", "❌ 请先在 params.yml server: 中配置 host 和 user")
            )
        else:
            log(tr("step5_connecting_server", "🔄 正在连接服务器 {host}:{port}...").format(
                host=conn.host, port=conn.port))
        kwargs: dict = dict(
            hostname=conn.host,
            port=conn.port,
            username=conn.user,
            timeout=timeout,
            look_for_keys=bool(conn.key_file),
            allow_agent=bool(conn.key_file),
        )
        if conn.key_file and Path(str(conn.key_file)).is_file():
            kwargs["key_filename"] = str(conn.key_file)
        elif conn.password:
            kwargs["password"] = conn.password
            kwargs["look_for_keys"] = False
            kwargs["allow_agent"] = False
        if conn.proxy_command:
            kwargs["sock"] = paramiko.ProxyCommand(conn.proxy_command)
        last_exc: Optional[Exception] = None
        for attempt in range(1, retries + 1):
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            try:
                # [EN] Suppress paramiko's raw traceback printed directly to
                # stderr by Transport (not via the logging module).
                # 屏蔽 paramiko Transport 直接写入 stderr 的原始 traceback。
                # [EN] Suppress the raw traceback written to stderr by paramiko Transport.
                with open(os.devnull, "w") as _devnull, \
                     contextlib.redirect_stderr(_devnull):
                    ssh.connect(**kwargs)
                self._ssh = ssh
                self._conn_args = (conn.host, conn.port, conn.user, conn.password)
                if attempt > 1:
                    log(tr("connect_retry_success", "✅ 第 {n} 次重试后连接成功").format(n=attempt - 1))
                else:
                    log(tr("connect_success_log", "✅ 连接服务器成功"))
                return
            except Exception as exc:
                last_exc = exc
                if _is_transient_error(exc) and attempt < retries:
                    delay = attempt * 2
                    log(tr(
                        "connect_retry_transient",
                        "⚠️ 瞬态网络错误（{error}），{delay}s 后第 {n} 次重试...",
                    ).format(error=exc, delay=delay, n=attempt + 1))
                    time.sleep(delay)
                    continue
                break
        # [EN] Build a helpful error message with common cause suggestions.
        # 构建包含常见原因提示的错误信息。
        # [EN] Build an error message that includes common-cause hints.
        hint = _connect_error_hint(last_exc, cfg.ssh_config_host)
        if cfg.ssh_config_host:
            raise ConnectionError(
                tr(
                    "step5_connect_ssh_config_failed",
                    "❌ 通过 SSH 配置 [{alias}] 连接失败：{error}{hint}",
                ).format(alias=cfg.ssh_config_host, error=last_exc, hint=hint)
            ) from last_exc
        raise ConnectionError(
            tr("step5_connect_failed", "❌ 连接服务器失败：{error}{hint}").format(
                error=last_exc, hint=hint)
        ) from last_exc

    def is_alive(self) -> bool:
        """当前 SSH 传输层是否仍处于活动状态。

        [EN] Whether the current SSH transport layer is still active.
        """
        if self._ssh is None:
            return False
        transport = self._ssh.get_transport()
        return transport is not None and transport.is_active()

    def ensure_connected(self, *, log: LogFn = _noop) -> None:
        """若连接已断开则自动重连。

        [EN] Automatically reconnect if the connection has been dropped.
        """
        if not self.is_alive():
            log(tr("ssh_connection_lost_reconnect", "⚠️ SSH 连接已断开，尝试重新连接..."))
            self.connect(log=log)

    def close(self) -> None:
        """关闭 SSH 连接并释放底层 socket。

        [EN] Close the SSH connection and release the underlying socket.
        """
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

        [EN] Execute a shell script on the remote host with streaming log output.

        Returns the process exit code.
        """
        self.ensure_connected(log=log)
        quoted_remote_dir = shlex.quote(remote_dir)
        quoted_script_name = shlex.quote(script_name)
        cmd = f"cd {quoted_remote_dir} && (chmod +x {quoted_script_name} 2>/dev/null || true) && bash {quoted_script_name}"
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
        """执行任意远程命令，返回 ``(stdout, stderr, exit_code)``。

        [EN] Execute an arbitrary remote command, returning ``(stdout, stderr, exit_code)``.
        """
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
        """列出远程目录下的文件名。

        [EN] List file names in the remote directory.
        """
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

    # Files / extensions that must have \r stripped before upload
    # (Windows-edited shell scripts, Fortran namelists, and input files)
    _UNIX_EOL_FILES = frozenset({"server.sh", "local.sh", "export.sh", "ww3.slurm", "ww3_ntfy_watch.sh"})
    _UNIX_EOL_EXTS = frozenset({".nml", ".inp"})

    def _put_file(self, sftp, local_file: str, remote_file: str) -> None:
        fname = os.path.basename(local_file)
        _, ext = os.path.splitext(fname)
        if fname in self._UNIX_EOL_FILES or ext.lower() in self._UNIX_EOL_EXTS:
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
                return
        sftp.put(local_file, remote_file)

    def upload_folder(
        self,
        local_dir: str,
        remote_dir: str,
        *,
        log: LogFn = _noop,
    ) -> None:
        """通过 SFTP 递归上传本地目录到 ``remote_dir``。

        上传前会将 ``server.sh`` 等脚本规范为 LF 换行。

        [EN] Recursively upload a local directory to ``remote_dir`` via SFTP.

        Scripts such as ``server.sh`` are normalized to LF line endings before upload.
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
                # [EN] Use posixpath for remote Linux paths; convert Windows-style rel to POSIX
                rel_posix = rel.replace(os.sep, "/") if os.sep != "/" else rel
                remote_path = posixpath.join(remote_dir, rel_posix) if rel_posix != "." else remote_dir
                try:
                    self._ensure_remote_dir(sftp, remote_path)
                except Exception as exc:
                    log(tr("ssh_remote_mkdir_failed", "⚠️ 无法创建远程目录 {path}: {error}").format(path=remote_path, error=exc))
                    continue

                for fname in files:
                    local_file = os.path.join(root, fname)
                    remote_file = posixpath.join(remote_path, fname)
                    try:
                        self._put_file(sftp, local_file, remote_file)
                        uploaded += 1
                        log(f"  ↑ {posixpath.join(rel_posix, fname) if rel_posix != '.' else fname}  [{uploaded}/{total_files}]")
                    except Exception as exc:
                        log(tr("ssh_upload_file_failed", "❌ 上传 {name} 失败: {error}").format(name=fname, error=exc))
        finally:
            sftp.close()
        log(tr("upload_complete", "✅ 上传完成，共 {count} 个文件 → {path}").format(count=uploaded, path=remote_dir))

    def upload_matching_files(
        self,
        local_dir: str,
        remote_dir: str,
        pattern_fn: Callable[[str], bool],
        *,
        recursive: bool = False,
        log: LogFn = _noop,
    ) -> int:
        """Upload files matching ``pattern_fn`` from ``local_dir`` to ``remote_dir``."""
        self.ensure_connected(log=log)
        if remote_dir.startswith("~"):
            remote_dir = remote_dir.replace("~", f"/home/{self._config.user}", 1)

        sftp = self._sftp()
        uploaded = 0
        try:
            self._ensure_remote_dir(sftp, remote_dir)
            walker: Iterator[tuple[str, list[str], list[str]]]
            if recursive:
                walker = os.walk(local_dir)
            else:
                names = os.listdir(local_dir)
                files = [name for name in names if os.path.isfile(os.path.join(local_dir, name))]
                walker = iter([(local_dir, [], files)])

            for root, _dirs, files in walker:
                rel = os.path.relpath(root, local_dir)
                # [EN] Use posixpath for remote Linux paths; convert Windows-style rel to POSIX
                rel_posix = rel.replace(os.sep, "/") if os.sep != "/" else rel
                remote_path = remote_dir if rel_posix == "." else posixpath.join(remote_dir, rel_posix)
                self._ensure_remote_dir(sftp, remote_path)
                for fname in files:
                    rel_file = fname if rel_posix == "." else posixpath.join(rel_posix, fname)
                    if not pattern_fn(rel_file):
                        continue
                    local_file = os.path.join(root, fname)
                    remote_file = posixpath.join(remote_path, fname)
                    self._put_file(sftp, local_file, remote_file)
                    uploaded += 1
                    log(f"  ↑ {rel_file}")
        finally:
            sftp.close()
        return uploaded

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

        [EN] Download files in ``remote_dir`` matching ``pattern_fn`` to ``local_dir``.

        Returns a list of local absolute paths that were successfully downloaded.
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
                log(tr("ssh_remote_no_matching_files", "⚠️ 远程目录未找到匹配的文件"))
                return downloaded

            os.makedirs(local_dir, exist_ok=True)
            for fname in matched:
                rpath = posixpath.join(remote_dir, fname)
                lpath = os.path.join(local_dir, fname)
                try:
                    size = sftp.stat(rpath).st_size or 0
                    log(f"⬇ {fname}  ({format_file_size(size)})")
                    last_pct = [0]

                    def _progress(transferred: int, total: int = size, name: str = fname) -> None:
                        pct = int(transferred / total * 100) if total else 0
                        if pct > last_pct[0]:
                            last_pct[0] = pct
                            log(f"  {name} ... {pct}%")

                    sftp.get(rpath, lpath, callback=_progress)
                    downloaded.append(lpath)
                    log(tr("download_file_complete", "✅ {name} 下载完成").format(name=fname))
                except Exception as exc:
                    log(tr("ssh_download_file_failed", "❌ 下载 {name} 失败: {error}").format(name=fname, error=exc))
        finally:
            sftp.close()
        return downloaded

    # ── status checks ─────────────────────────────────────────────────────────

    def check_completion(self, remote_dir: str, *, log: LogFn = _noop) -> str:
        """根据远程目录中的 ``success`` / ``fail`` 标记文件判断任务状态。

        返回 ``success``、``failed`` 或 ``running``。

        [EN] Determine task status from ``success`` / ``fail`` marker files in the
        remote directory.

        Returns ``success``, ``failed``, or ``running``.
        """
        self.ensure_connected(log=log)
        sftp = self._sftp()
        try:
            files = sftp.listdir(remote_dir)
        except IOError as exc:
            raise RuntimeError(f"无法访问远程目录 {remote_dir}: {exc}") from exc
        finally:
            sftp.close()
        if "success" in files:
            return "success"
        if "fail" in files:
            return "failed"
        return "running"

    def queue_status(self, *, log: LogFn = _noop) -> str:
        """执行 ``squeue -l`` 并返回标准输出文本。

        [EN] Execute ``squeue -l`` and return the standard output text.
        """
        out, err, _ = self.exec_command("squeue -l", log=log, timeout=10)
        if err:
            log(tr("ssh_squeue_error", "⚠️ squeue 错误: {error}").format(error=err))
        return out

    def cancel_job(self, job_id: str, *, log: LogFn = _noop) -> None:
        """通过 ``scancel`` 取消指定 SLURM 任务。

        [EN] Cancel the specified SLURM job via ``scancel``.
        """
        quoted_job_id = shlex.quote(str(job_id))
        out, err, code = self.exec_command(f"scancel {quoted_job_id}", log=log)
        if code == 0:
            log(tr("cancel_job_success", "✅ 已取消任务 {job_id}").format(job_id=job_id))
        else:
            log(tr("cancel_job_failed_detail", "❌ 取消任务 {job_id} 失败: {error}").format(job_id=job_id, error=err or out))

    def clear_remote_dir(self, remote_dir: str, *, log: LogFn = _noop) -> None:
        """清空 ``remote_dir`` 内所有文件与子目录（保留目录本身）。

        [EN] Remove all files and subdirectories inside ``remote_dir`` (keeping
        the directory itself).
        """
        quoted_remote_dir = shlex.quote(remote_dir)
        cmd = f"cd {quoted_remote_dir} && find . -mindepth 1 -maxdepth 1 -exec rm -rf -- {{}} +"
        log(tr("clear_remote_dir_start", "🗑 清空远程目录: {path}").format(path=remote_dir))
        out, err, code = self.exec_command(cmd, log=log, timeout=60)
        if code == 0:
            log(tr("clear_remote_dir_done", "✅ 已清空 {path}").format(path=remote_dir))
        else:
            message = err or out or f"exit code {code}"
            log(tr("clear_remote_dir_warning", "⚠️ 清空时有警告: {error}").format(error=message))
            raise RuntimeError(f"清空远程目录失败：{remote_dir}（{message}）")
