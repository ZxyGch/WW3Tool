"""远程 SSH/SFTP 操作基础设施。

提供同步 SSH 客户端，供 Step 5 上传工作目录、执行 ``server.sh``、下载结果等。
桌面端在自有线程中包装调用；CLI 直接同步调用。不依赖 Qt 或信号机制。

[EN] Remote SSH/SFTP operation infrastructure.

Provides a synchronous SSH client for Step 5 to upload the working directory,
execute ``server.sh``, download results, etc. The desktop layer wraps calls in
its own thread; CLI calls directly and synchronously. No dependency on Qt or
signal mechanisms.
"""

from .ssh_client import SshClient

__all__ = ["SshClient"]
