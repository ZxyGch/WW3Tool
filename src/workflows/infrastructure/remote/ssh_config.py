"""解析 OpenSSH 客户端配置（``~/.ssh/config``）。

设置页「使用 SSH 配置登录」只保存 Host 别名；连接时从此处解析
host / port / user / identityfile，不复制到 params.yml。

[EN] Parse OpenSSH client configuration (``~/.ssh/config``).

The settings-page "use SSH config login" option stores only a Host alias;
connection details are resolved at connect time and not copied into params.yml.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ...domain.config_models import ServerConfig


@dataclass(frozen=True)
class ResolvedSshConnection:
    """解析后的 SSH 连接参数。

    [EN] Resolved SSH connection parameters.
    """

    host: str
    port: int
    user: str
    key_file: Optional[Path] = None
    password: str = ""
    proxy_command: str = ""


def default_ssh_config_path() -> Path:
    return Path.home() / ".ssh" / "config"


def list_ssh_config_hosts(config_path: Path | None = None) -> list[str]:
    """列出 ``~/.ssh/config`` 中的 Host 别名（跳过 ``*`` 通配）。

    [EN] List Host aliases in ``~/.ssh/config`` (skipping ``*`` wildcards).
    """
    path = config_path or default_ssh_config_path()
    if not path.is_file():
        return []
    hosts: list[str] = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = re.match(r"^Host\s+(.+)$", line, flags=re.IGNORECASE)
        if not match:
            continue
        for token in match.group(1).split():
            if token == "*":
                continue
            if any(ch in token for ch in "*?"):
                continue
            if token not in hosts:
                hosts.append(token)
    return hosts


def resolve_ssh_config_host(alias: str, config_path: Path | None = None) -> ResolvedSshConnection:
    """按 Host 别名解析 ``~/.ssh/config``。

    [EN] Resolve ``~/.ssh/config`` by Host alias.
    """
    alias = str(alias or "").strip()
    if not alias:
        raise ValueError("SSH config Host 别名不能为空")

    path = config_path or default_ssh_config_path()
    if not path.is_file():
        raise FileNotFoundError(f"未找到 SSH 配置文件：{path}")

    try:
        import paramiko
    except ImportError as exc:
        raise RuntimeError("SSH 配置解析需要 paramiko，请先安装：pip install paramiko") from exc

    ssh_config = paramiko.SSHConfig()
    with path.open(encoding="utf-8", errors="replace") as handle:
        ssh_config.parse(handle)
    data = ssh_config.lookup(alias)

    host = str(data.get("hostname") or alias).strip()
    user = str(data.get("user") or "").strip()
    try:
        port = int(data.get("port") or 22)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"SSH 配置端口无效：{data.get('port')!r}") from exc

    identity = data.get("identityfile")
    key_file: Optional[Path] = None
    if identity:
        if isinstance(identity, (list, tuple)):
            identity = identity[0] if identity else None
        if identity:
            key_file = Path(os.path.expanduser(str(identity)))

    proxy_command = str(data.get("proxycommand") or "").strip()

    return ResolvedSshConnection(
        host=host,
        port=port,
        user=user,
        key_file=key_file,
        proxy_command=proxy_command,
    )


def resolve_server_connection(config: ServerConfig) -> ResolvedSshConnection:
    """将 ``ServerConfig`` 解析为实际连接参数（含 SSH 配置模式）。

    [EN] Resolve ``ServerConfig`` into actual connection parameters (including
    SSH-config mode).
    """
    if config.ssh_config_host:
        resolved = resolve_ssh_config_host(config.ssh_config_host)
        return ResolvedSshConnection(
            host=resolved.host,
            port=resolved.port,
            user=resolved.user or config.user,
            key_file=resolved.key_file or config.key_file,
            password=config.password,
            proxy_command=resolved.proxy_command,
        )
    return ResolvedSshConnection(
        host=str(config.host or "").strip(),
        port=int(config.port or 22),
        user=str(config.user or "").strip(),
        key_file=config.key_file,
        password=str(config.password or ""),
    )
