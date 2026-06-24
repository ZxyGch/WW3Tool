"""本地 WW3 执行服务：Python 直驱 WW3 可执行文件，跨平台支持，可停止。

``run_workflow()`` 完整复刻 ``local.sh`` 逻辑，用 Python 直接调用 ww3_grid / ww3_prnc /
ww3_strt / ww3_shel / ww3_multi / ww3_ounp / ww3_trnc / ww3_ounf，无需 bash。
``run_tool()`` 用于单独运行后处理工具。``stop()`` 终止当前进程树。

[EN] Local WW3 execution service: Python-native WW3 workflow driver, cross-platform.

``run_workflow()`` replicates ``local.sh`` logic, directly invoking WW3 executables via
Python subprocess — no bash needed. ``run_tool()`` runs individual post-processing tools.
``stop()`` terminates the current process tree.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import threading
from pathlib import Path
from typing import Callable, Optional

from ...support.translations import tr

LogCallback = Callable[[str], None]

# 各工具运行前需存在的输出文件（任一即可）。
# [EN] Output files that must exist before each tool runs (any one is sufficient).
_TOOL_PRECHECK = {
    "ww3_ounf": ["out_grd.ww3"],
    "ww3_ounp": ["out_pnt.ww3", "out_grd.ww3"],
    "ww3_trnc": ["out_grd.ww3"],
}

_IS_WIN = os.name == "nt"


def _find_bash() -> str | None:
    """Locate a usable ``bash`` executable on the current platform.

    Search order (Windows):
    1. ``bash`` on ``PATH`` (e.g. Git Bash added to PATH, MSYS2, Cygwin)
    2. Git for Windows default install paths
    3. WSL ``bash.exe``

    On POSIX, simply return ``"bash"`` (assumed available).
    """
    if not _IS_WIN:
        return "bash"
    # 1. Already on PATH?
    found = shutil.which("bash")
    if found:
        return found
    # 2. Git for Windows default locations
    for candidate in (
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files (x86)\Git\bin\bash.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Git\bin\bash.exe"),
    ):
        if os.path.isfile(candidate):
            return candidate
    # 3. WSL
    wsl_bash = shutil.which("wsl")
    if wsl_bash:
        return None  # caller should use [wsl, bash, ...] — handled separately
    return None


def _tool_exe(tool: str) -> str:
    """Return the platform-appropriate executable name (append ``.exe`` on Windows)."""
    if _IS_WIN and not tool.lower().endswith(".exe"):
        return tool + ".exe"
    return tool


def _move_if(src: Path, dst: Path) -> None:
    """Move *src* to *dst* if *src* exists."""
    if src.is_file():
        shutil.move(str(src), str(dst))


def _run_log_callback(workdir: Path, log: LogCallback) -> LogCallback:
    """Return a log callback that mirrors messages to ``workdir/run.log``."""
    run_log = workdir / "run.log"
    try:
        run_log.touch(exist_ok=True)
    except Exception as exc:
        log(tr("local_run_log_write_failed", "⚠️ 无法写入 run.log：{error}").format(error=exc))
        return log

    def write(message: str) -> None:
        text = str(message)
        try:
            with run_log.open("a", encoding="utf-8") as fh:
                fh.write(text + "\n")
        except Exception:
            pass
        log(text)

    return write


class LocalRunService:
    """运行本地 WW3 脚本/工具并支持停止（持有当前子进程）。

    [EN] Run local WW3 scripts/tools with stop support (holds the current subprocess).
    """

    def __init__(self) -> None:
        self._proc: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()

    def _stream(self, cmd: list[str], cwd: str, bin_dir: str, log: LogCallback) -> int:
        env = os.environ.copy()
        if bin_dir:
            env["PATH"] = bin_dir + os.pathsep + env.get("PATH", "")
        popen_kwargs: dict = dict(
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
        )
        if _IS_WIN:
            # [EN] On Windows, use CREATE_NEW_PROCESS_GROUP for stop support
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_kwargs["close_fds"] = True
            popen_kwargs["start_new_session"] = True
        proc = subprocess.Popen(cmd, **popen_kwargs)
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
        """运行 ``<workdir>/local.sh``（缺失时回退 ``fallback_script``）。返回退出码（-1=脚本缺失）。

        [EN] Run ``<workdir>/local.sh`` (falls back to ``fallback_script`` if missing). Returns exit code (-1 = script not found).
        """
        script = Path(workdir) / "local.sh"
        if not script.is_file() and fallback_script and Path(fallback_script).is_file():
            script = Path(fallback_script)
        if not script.is_file():
            log(tr("local_script_not_found", "❌ 找不到本地脚本：{path}").format(path=script))
            return -1
        log(tr("local_run_start", "▶️ 开始执行本地 WW3 运行..."))
        bash = _find_bash()
        if bash is None:
            log(tr("local_run_bash_not_found", "❌ 找不到 bash（请安装 Git for Windows 并确保 bash 在 PATH 中）"))
            return -1
        try:
            return self._stream([bash, str(script)], str(workdir), bin_dir, log)
        except FileNotFoundError:
            log(tr("local_run_bash_start_failed", "❌ 无法启动 bash：{path}").format(path=bash))
            return -1

    def run_tool(self, tool: str, workdir: str, bin_dir: str, log: LogCallback) -> int:
        """运行 ww3_ounf/ounp/trnc（前置检查输出文件）。返回退出码（-1=跳过/未找到命令）。

        [EN] Run ww3_ounf/ounp/trnc (pre-checks output files). Returns exit code (-1 = skipped/command not found).
        """
        log = _run_log_callback(Path(workdir), log)
        checks = _TOOL_PRECHECK.get(tool, [])
        if checks and not any((Path(workdir) / name).exists() for name in checks):
            log(tr("local_run_output_file_missing", "❌ 未找到输出文件 {files}，跳过 {tool}").format(files=" 或 ".join(checks), tool=tool))
            return -1
        # [EN] On Windows, look for .exe variant
        exe_name = _tool_exe(tool)
        cmd_path = os.path.join(bin_dir, exe_name) if bin_dir else exe_name
        use_abs = bool(bin_dir) and os.path.isfile(cmd_path) and os.access(cmd_path, os.X_OK)
        if not use_abs and bin_dir:
            # [EN] Fallback: try without .exe (might be a script or symlink)
            alt_path = os.path.join(bin_dir, tool)
            if os.path.isfile(alt_path) and os.access(alt_path, os.X_OK):
                cmd_path = alt_path
                use_abs = True
        log(tr("local_run_tool_start", "▶️ 开始执行：{tool}").format(tool=tool))
        try:
            return self._stream([cmd_path] if use_abs else [exe_name], str(workdir), bin_dir, log)
        except FileNotFoundError:
            log(tr("local_run_cmd_not_found", "❌ 找不到命令：{cmd}，请填写 WW3 bin 路径或设置 PATH").format(cmd=exe_name))
            return -1

    def _resolve_tool(self, tool: str, bin_dir: str) -> str:
        """Return absolute path or plain name for *tool*, handling ``.exe`` on Windows."""
        exe = _tool_exe(tool)
        if bin_dir:
            for name in (exe, tool):  # try .exe first, then bare
                full = os.path.join(bin_dir, name)
                if os.path.isfile(full):
                    return full
        return exe  # rely on PATH

    def _run_tool_in(self, tool: str, workdir: str, bin_dir: str, log: LogCallback) -> int:
        """Run a single WW3 tool in *workdir*. Returns exit code."""
        cmd = self._resolve_tool(tool, bin_dir)
        try:
            return self._stream([cmd], workdir, bin_dir, log)
        except FileNotFoundError:
            log(tr("local_run_cmd_not_found", "❌ 找不到命令：{cmd}，请填写 WW3 bin 路径或设置 PATH").format(cmd=cmd))
            return -1

    # ---- WW3 workflow steps (Python-native, no bash) ----

    def _run_prnc_fields(self, workdir: str, bin_dir: str, log: LogCallback) -> int:
        """Run ``ww3_prnc`` for all forcing namelists present. Returns last non-zero rc or 0."""
        wp = Path(workdir)
        has_multi = any(
            (wp / n).exists()
            for n in ("ww3_prnc_current.nml", "ww3_prnc_level.nml", "ww3_prnc_ice.nml", "ww3_prnc_ice1.nml")
        )
        if not has_multi:
            log("")
            log("=" * 30 + " " + tr("local_run_step_prnc", "运行 ww3_prnc") + " " + "=" * 30)
            return self._run_tool_in("ww3_prnc", workdir, bin_dir, log)

        # 1) default ww3_prnc.nml (wind)
        log("")
        log("=" * 30 + " " + tr("local_run_step_prnc_wind", "运行 ww3_prnc (wind)") + " " + "=" * 30)
        rc = self._run_tool_in("ww3_prnc", workdir, bin_dir, log)
        if rc != 0:
            return rc
        # rename to _wind
        wind_nml = wp / "ww3_prnc.nml"
        wind_bak = wp / "ww3_prnc_wind.nml"
        if wind_nml.exists():
            wind_nml.rename(wind_bak)

        # 2) process extra forcing files
        for tag in ("current", "level", "ice", "ice1"):
            tag_nml = wp / f"ww3_prnc_{tag}.nml"
            if not tag_nml.exists():
                continue
            log("")
            log("=" * 30 + " " + tr("local_run_step_prnc_tag", "运行 ww3_prnc ({tag})").format(tag=tag) + " " + "=" * 30)
            tag_nml.rename(wp / "ww3_prnc.nml")
            rc = self._run_tool_in("ww3_prnc", workdir, bin_dir, log)
            (wp / "ww3_prnc.nml").rename(tag_nml)
            if rc != 0:
                break

        # 3) restore wind nml
        if wind_bak.exists():
            wind_bak.rename(wp / "ww3_prnc.nml")
        return rc

    def _run_shel_with_fallback(self, workdir: str, bin_dir: str, log: LogCallback, nprocs: int) -> int:
        """Run ``mpirun ww3_shel`` with direct fallback. Returns exit code."""
        shel = self._resolve_tool("ww3_shel", bin_dir)
        # try mpirun
        mpi = shutil.which("mpirun") or shutil.which("mpiexec")
        if mpi:
            log("")
            log("=" * 30 + " " + tr("local_run_step_mpi_shel", "运行 {mpi} -n {nprocs} ww3_shel").format(mpi=os.path.basename(mpi), nprocs=nprocs) + " " + "=" * 30)
            try:
                rc = self._stream([mpi, "-n", str(nprocs), shel], workdir, bin_dir, log)
            except FileNotFoundError:
                rc = -1
            if rc == 0:
                return 0
            log(tr("local_run_mpi_fallback", "⚠️ mpirun ww3_shel 失败 (rc={rc})，回退到直接运行 ww3_shel").format(rc=rc))

        log("")
        log("=" * 30 + " " + tr("local_run_step_shel_direct", "运行 ww3_shel (direct)") + " " + "=" * 30)
        try:
            return self._stream([shel], workdir, bin_dir, log)
        except FileNotFoundError:
            log(tr("local_run_shel_not_found", "❌ 找不到 ww3_shel"))
            return -1

    def run_workflow(self, workdir: str, bin_dir: str, log: LogCallback) -> int:
        """Execute the full WW3 workflow in Python (no bash needed).

        Replicates ``local.sh``: ww3_grid → ww3_prnc → ww3_strt → ww3_shel →
        ww3_ounp/trnc/ounf, with nested-grid support.

        [EN] Python-native WW3 workflow driver — replaces ``bash local.sh``.
        """
        import time

        wp = Path(workdir)
        success_mark = wp / "success"
        fail_mark = wp / "fail"
        try:
            success_mark.unlink(missing_ok=True)
            fail_mark.unlink(missing_ok=True)
        except Exception:
            pass
        log = _run_log_callback(wp, log)
        log(tr("local_run_start", "▶️ 开始执行本地 WW3 运行..."))
        start_t = time.time()

        # MPI process count
        nprocs = int(os.environ.get("WW3_MPI_NPROCS", "0") or 0)
        if nprocs <= 0:
            try:
                nprocs = os.cpu_count() or 1
            except Exception:
                nprocs = 1
        log(tr("local_run_mpi_nprocs", "使用 MPI_NPROCS={nprocs}").format(nprocs=nprocs))

        from workflows.infrastructure.ww3.nested_level_dirs import is_nested_workdir

        nested = is_nested_workdir(wp)

        if nested:
            rc = self._workflow_nested(wp, bin_dir, log, nprocs)
        else:
            rc = self._workflow_regular(wp, bin_dir, log, nprocs)

        elapsed = time.time() - start_t
        if rc == 0:
            log(tr("step5_workflow_done", "✅ 本地 WW3 运行完成 ({elapsed:.1f}s)").format(elapsed=elapsed))
            try:
                success_mark.touch()
            except Exception:
                pass
        else:
            log(tr("step5_workflow_failed", "❌ 本地 WW3 运行失败 (rc={rc}, {elapsed:.1f}s)").format(rc=rc, elapsed=elapsed))
            try:
                fail_mark.touch()
            except Exception:
                pass
        return rc

    # ---- regular grid workflow ----

    def _workflow_regular(self, wp: Path, bin_dir: str, log: LogCallback, nprocs: int) -> int:
        wd = str(wp)
        log("")
        log("=" * 30 + " " + tr("local_run_step_grid", "运行 ww3_grid") + " " + "=" * 30)
        rc = self._run_tool_in("ww3_grid", wd, bin_dir, log)
        if rc != 0:
            return rc

        rc = self._run_prnc_fields(wd, bin_dir, log)
        if rc != 0:
            return rc

        log("")
        log("=" * 30 + " " + tr("local_run_step_strt", "运行 ww3_strt") + " " + "=" * 30)
        rc = self._run_tool_in("ww3_strt", wd, bin_dir, log)
        if rc != 0:
            return rc

        rc = self._run_shel_with_fallback(wd, bin_dir, log, nprocs)
        if rc != 0:
            return rc

        return self._run_post_processing(wd, bin_dir, log)

    # ---- nested grid workflow ----

    def _workflow_nested(self, wp: Path, bin_dir: str, log: LogCallback, nprocs: int) -> int:
        from workflows.infrastructure.ww3.nested_level_dirs import list_nested_level_entries

        levels = list_nested_level_entries(wp)
        if not levels:
            log(tr("nested_grid_folders_not_found", "❌ 未找到 level* 网格目录，请先生成嵌套网格"))
            return 1

        for level_path, _idx in levels:
            label = level_path.name
            sub = str(level_path)
            log("")
            log("=" * 30 + " " + tr("local_run_step_grid_label", "运行 ww3_grid ({label})").format(label=label) + " " + "=" * 30)
            rc = self._run_tool_in("ww3_grid", sub, bin_dir, log)
            if rc != 0:
                return rc
            rc = self._run_prnc_fields(sub, bin_dir, log)
            if rc != 0:
                return rc
            log("")
            log("=" * 30 + " " + tr("local_run_step_strt_label", "运行 ww3_strt ({label})").format(label=label) + " " + "=" * 30)
            rc = self._run_tool_in("ww3_strt", sub, bin_dir, log)
            if rc != 0:
                return rc

        staged = ("mod_def", "restart", "wind", "current", "level", "ice", "ice1")
        for level_path, _idx in levels:
            lv = level_path.name
            for stem in staged:
                _move_if(level_path / f"{stem}.ww3", wp / f"{stem}.{lv}")

        # Run ww3_multi
        multi = self._resolve_tool("ww3_multi", bin_dir)
        mpi = shutil.which("mpirun") or shutil.which("mpiexec")
        if mpi:
            log("")
            log("=" * 30 + " " + tr("local_run_step_mpi_multi", "运行 {mpi} -n {nprocs} ww3_multi").format(mpi=os.path.basename(mpi), nprocs=nprocs) + " " + "=" * 30)
            rc = self._stream([mpi, "-n", str(nprocs), multi], str(wp), bin_dir, log)
        else:
            log("")
            log("=" * 30 + " " + tr("local_run_step_multi_direct", "运行 ww3_multi (direct)") + " " + "=" * 30)
            try:
                rc = self._stream([multi], str(wp), bin_dir, log)
            except FileNotFoundError:
                log(tr("local_run_multi_not_found", "❌ 找不到 ww3_multi"))
                return -1
        if rc != 0:
            return rc

        finest_path = levels[-1][0]
        finest = finest_path.name
        _move_if(wp / f"out_grd.{finest}", finest_path / "out_grd.ww3")
        _move_if(wp / f"mod_def.{finest}", finest_path / "mod_def.ww3")
        _move_if(wp / f"out_pnt.{finest}", finest_path / "out_pnt.ww3")
        _move_if(wp / f"track_o.{finest}", finest_path / "track_o.ww3")

        return self._run_post_processing(str(finest_path), bin_dir, log, points_list_dir=str(wp))

    # ---- post-processing ----

    def _run_post_processing(
        self,
        workdir: str,
        bin_dir: str,
        log: LogCallback,
        *,
        points_list_dir: str | None = None,
    ) -> int:
        wp = Path(workdir)
        points_root = Path(points_list_dir) if points_list_dir else wp
        rc = 0
        if (points_root / "points.list").exists():
            log("")
            log("=" * 30 + " " + tr("local_run_step_ounp", "运行 ww3_ounp") + " " + "=" * 30)
            rc = self._run_tool_in("ww3_ounp", workdir, bin_dir, log)
            if rc != 0:
                return rc

        if rc == 0 and (wp / "track_i.ww3").exists():
            log("")
            log("=" * 30 + " " + tr("local_run_step_trnc", "运行 ww3_trnc") + " " + "=" * 30)
            rc = self._run_tool_in("ww3_trnc", workdir, bin_dir, log)
            if rc != 0:
                return rc

        if rc == 0:
            log("")
            log("=" * 30 + " " + tr("local_run_step_ounf", "运行 ww3_ounf") + " " + "=" * 30)
            rc = self._run_tool_in("ww3_ounf", workdir, bin_dir, log)
        return rc

    def is_running(self) -> bool:
        with self._lock:
            return self._proc is not None

    def stop(self) -> bool:
        """终止当前进程组；无运行中进程返回 False。

        [EN] Terminate the current process group; returns False if no process is running.
        """
        with self._lock:
            proc = self._proc
        if proc is None:
            return False
        try:
            if _IS_WIN:
                # [EN] On Windows, terminate the process tree via taskkill
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    capture_output=True,
                )
            else:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except Exception:
            try:
                proc.terminate()
            except Exception:
                return False
        return True
