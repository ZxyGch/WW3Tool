"""本地 WW3 执行服务：在工作目录运行 ``local.sh`` 与 ww3_ounf/ounp/trnc，可停止。

迁移自 src ``home_local_run``：``bash local.sh``（WW3 bin 目录加入 ``PATH``，新会话便于整树
停止），逐行回调日志；ww3_ounf/ounp/trnc 运行前检查 out_grd.ww3 / out_pnt.ww3。
``stop()`` 通过 ``killpg`` 结束当前进程组。
"""

from __future__ import annotations

import os
import signal
import subprocess
import threading
from pathlib import Path
from typing import Callable, Optional

LogCallback = Callable[[str], None]

# 各工具运行前需存在的输出文件（任一即可）。
_TOOL_PRECHECK = {
    "ww3_ounf": ["out_grd.ww3"],
    "ww3_ounp": ["out_pnt.ww3", "out_grd.ww3"],
    "ww3_trnc": ["out_grd.ww3"],
}


class LocalRunService:
    """运行本地 WW3 脚本/工具并支持停止（持有当前子进程）。"""

    def __init__(self) -> None:
        self._proc: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()

    def _stream(self, cmd: list[str], cwd: str, bin_dir: str, log: LogCallback) -> int:
        env = os.environ.copy()
        if bin_dir:
            env["PATH"] = bin_dir + os.pathsep + env.get("PATH", "")
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
            close_fds=True,
            start_new_session=True,
        )
        with self._lock:
            self._proc = proc
        try:
            assert proc.stdout is not None
            for line in iter(proc.stdout.readline, ""):
                if not line:
                    break
                stripped = line.rstrip()
                if stripped:
                    log(stripped)
            return proc.wait()
        finally:
            with self._lock:
                self._proc = None

    def run_script(self, workdir: str, bin_dir: str, log: LogCallback, *, fallback_script: str | None = None) -> int:
        """运行 ``<workdir>/local.sh``（缺失时回退 ``fallback_script``）。返回退出码（-1=脚本缺失）。"""
        script = Path(workdir) / "local.sh"
        if not script.is_file() and fallback_script and Path(fallback_script).is_file():
            script = Path(fallback_script)
        if not script.is_file():
            log(f"❌ 找不到本地脚本：{script}")
            return -1
        log("▶️ 开始执行本地 WW3 运行...")
        try:
            return self._stream(["bash", str(script)], str(workdir), bin_dir, log)
        except FileNotFoundError:
            log("❌ 找不到 bash 命令，无法执行脚本")
            return -1

    def run_tool(self, tool: str, workdir: str, bin_dir: str, log: LogCallback) -> int:
        """运行 ww3_ounf/ounp/trnc（前置检查输出文件）。返回退出码（-1=跳过/未找到命令）。"""
        checks = _TOOL_PRECHECK.get(tool, [])
        if checks and not any((Path(workdir) / name).exists() for name in checks):
            log(f"❌ 未找到输出文件 {' 或 '.join(checks)}，跳过 {tool}")
            return -1
        cmd_path = os.path.join(bin_dir, tool) if bin_dir else tool
        use_abs = bool(bin_dir) and os.path.isfile(cmd_path) and os.access(cmd_path, os.X_OK)
        log(f"▶️ 开始执行：{tool}")
        try:
            return self._stream([cmd_path] if use_abs else [tool], str(workdir), bin_dir, log)
        except FileNotFoundError:
            log(f"❌ 找不到命令：{tool}，请填写 WW3 bin 路径或设置 PATH")
            return -1

    def is_running(self) -> bool:
        with self._lock:
            return self._proc is not None

    def stop(self) -> bool:
        """终止当前进程组；无运行中进程返回 False。"""
        with self._lock:
            proc = self._proc
        if proc is None:
            return False
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except Exception:
            try:
                proc.terminate()
            except Exception:
                return False
        return True
