#!/usr/bin/env python3
"""WW3Tool 统一入口（实现位于 src/）。

一个入口通吃三种使用方式，并统一负责环境搭建（虚拟环境 / 依赖 / sys.path）：

    python3 run.py                       → 启动 Desktop 图形界面（默认）
    python3 run.py shell [params.yml]    → 启动交互式 REPL（推荐日常操作）
    python3 run.py <子命令> [选项] [工作目录]  → 无界面 CLI（适合脚本与自动化）

不带子命令执行 ``python3 run.py --help`` 时，打印命令参考（与 ``shell`` 内 ``help`` 相同）。

**重要**：仓库根目录 ``params.yml`` 是模板，不允许直接用于运行。
用 ``workdir <路径>`` 从模板创建或加载工作目录（CLI：
``python3 run.py workdir <路径>``）。其余命令可跟可选的 ``[工作目录]``，
省略时使用当前目录。

典型流程：

    workdir → run-workflow → local-run
                              └→ upload → submit → check-status → download-results

配置管理
  workdir <路径>           创建或加载工作目录（shell）；CLI 为独立子命令
  validate [工作目录]      校验 params.yml
  config [工作目录]        显示配置摘要
  print-params [工作目录]  输出 params.yml 内容

预处理（merge-forcing 除外均可跟 [工作目录]）
  prepare-forcing          Step 1：准备强迫场
  merge-forcing <输入.nc> [...] -o <输出.nc> [--time-range ...] [--bbox ...]
                           独立工具：校验并合并强迫场 NetCDF（无需工作目录）
  generate-grid            Step 2：生成计算网格
  prepare-ww3              仅生成 WW3 namelist
  recommend-cfl            按 CFL 推荐时间步长并写回配置
  recommend-grid           推荐网格间距/分辨率并写回配置
  run-workflow             完整预处理：强迫场 → 网格 → WW3 namelist
  local-run                执行 local.sh（本地跑 WW3）

后处理 / 绘图（plot: 段）
  plot-wave-maps [--contour] / plot-spectrum [--mode ...] [--station N]
  plot-jason3 / plot-jason3-swh / download-jason3 / plot-ndbc [--download]

远程运维（server: 段）
  connect-test / ssh / slurm-idle / list-files
  confirm-slurm [full|half]        写 server.sh；full/half 自动选取空闲 CPU
  upload --confirm / submit [--script server.sh]
  check-status / queue-status
  download-results [--nested] / download-log
  clear-remote --confirm / cancel-job <job_id>

辅助
  print-example            打印示例 params.yml
  help / exit              仅 shell 模式

----------------------------------------------------------------------
使用方式
----------------------------------------------------------------------

    python3 run.py shell [params.yml]    交互式 REPL（命令不带 ``[工作目录]`` 时沿用已加载目录）
    python3 run.py <子命令> [选项] [工作目录]  无界面 CLI（每条命令单独指定工作目录）

----------------------------------------------------------------------
全局选项
----------------------------------------------------------------------
--lang <语言代码>   切换输出语言（zh_CN / en_US），三种模式均可用。

----------------------------------------------------------------------
退出码
----------------------------------------------------------------------
0  成功
1  运行时异常 / 任务失败 / 依赖初始化失败
2  参数或 YAML 配置错误
3  破坏性远程操作未加 --confirm

[EN] Unified WW3Tool entry point (implementation lives in src/).

One entry point for three usage modes, and the single place responsible for
runtime setup (venv / dependencies / sys.path):

    python3 run.py                       -> Launch the Desktop GUI (default)
    python3 run.py shell [params.yml]    -> Interactive REPL
    python3 run.py <subcommand> [opts] [workdir]  -> Headless CLI

Running ``python3 run.py --help`` without a subcommand prints the command
reference (same as ``help`` inside ``shell``).

**Important**: The repository-root ``params.yml`` is a template and must not be
run directly. Use ``workdir <path>`` to create or load a workdir (CLI:
``python3 run.py workdir <path>``). Other commands accept an optional ``[workdir]``;
the current directory is used when omitted.

Typical flow:

    workdir -> run-workflow -> local-run
                               -> upload -> submit -> check-status -> download-results

Configuration
  workdir <path>           Create/load workdir (shell); standalone CLI subcommand
  validate [workdir]       Validate params.yml
  config [workdir]         Show configuration summary
  print-params [workdir]   Print params.yml

Preprocessing (all except merge-forcing accept optional [workdir])
  prepare-forcing / generate-grid / prepare-ww3 / recommend-cfl / recommend-grid
  run-workflow / local-run
  merge-forcing <in.nc> [...] -o <out.nc> [--time-range ...] [--bbox ...]  (standalone)

Post-processing / plotting (plot: section)
  plot-wave-maps [--contour] / plot-spectrum [--mode ...] [--station N]
  plot-jason3 / plot-jason3-swh / download-jason3 / plot-ndbc [--download]

Remote operations (server: section)
  connect-test / ssh / slurm-idle / list-files
  confirm-slurm [full|half]        Write server.sh; full/half auto-pick idle CPUs
  upload --confirm / submit [--script server.sh]
  check-status / queue-status / download-results [--nested] / download-log
  clear-remote --confirm / cancel-job <job_id>

Auxiliary
  print-example
  help / exit              Shell mode only

----------------------------------------------------------------------
Usage modes
----------------------------------------------------------------------

    python3 run.py shell [params.yml]    Interactive REPL (reuses loaded workdir when omitted)
    python3 run.py <subcommand> [opts] [workdir]  Headless CLI (workdir per invocation)

----------------------------------------------------------------------
Global options
----------------------------------------------------------------------
--lang <code>   Switch output language (zh_CN / en_US); available in all modes.

----------------------------------------------------------------------
Exit codes
----------------------------------------------------------------------
0  Success
1  Runtime exception / task failure / dependency initialization failure
2  Parameter or YAML configuration error
3  Destructive remote operation without --confirm
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import sysconfig
from pathlib import Path


ROOT = Path(__file__).resolve().parent
ENTRY_SCRIPT = ROOT / "run.py"
REQUIREMENTS_FILE = ROOT / "src" / "requirements.txt"
VENV_DIR = ROOT / ".venv"

# 无需完整虚拟环境/依赖即可执行的轻量 CLI 子命令。
# [EN] Lightweight CLI subcommands that don't require the full venv/dependencies.
_LIGHT_CLI_COMMANDS = {"--help", "-h", "print-example", "workdir"}

# 项目所需的全部依赖包及其对应的导入模块名。
# [EN] All required packages and their importable module names.
_REQUIRED_IMPORTS = {
    "numpy": "numpy",
    "netCDF4": "netCDF4",
    "pandas": "pandas",
    "matplotlib": "matplotlib",
    "cartopy": "cartopy",
    "Pillow": "PIL",
    "scipy": "scipy",
    "scikit-image": "skimage",
    "opencv-python": "cv2",
    "paramiko": "paramiko",
    "PyQt6": "PyQt6.QtWidgets",
    "PyQt6-Fluent-Widgets": "qfluentwidgets",
    "requests": "requests",
    "PyYAML": "yaml",
    "pyfiglet": "pyfiglet",
}

# 用于在子进程中检测缺失依赖的内联脚本。
# [EN] Inline script to detect missing dependencies in a subprocess.
_CHECK_SCRIPT = """\
import importlib.util
import json
import sys

missing = []
for name, module in json.loads(sys.argv[1]).items():
    try:
        ok = importlib.util.find_spec(module) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        ok = False
    if not ok:
        missing.append(name)
print(json.dumps(missing))
"""


def _bootstrap_src_imports() -> None:
    """将 src 加入 sys.path，以便 import workflows、desktop 等模块。

    [EN] Add src to sys.path so workflows and desktop can be imported.
    """
    src_str = str(ROOT / "src")
    if src_str not in sys.path:
        sys.path.insert(0, src_str)


def _tr(key: str, default: str) -> str:
    """Translate bootstrap messages after src has been added to sys.path."""
    try:
        from workflows.support.translations import tr

        return tr(key, default)
    except Exception:
        return default


def _extract_lang(argv: list[str]) -> tuple[str | None, list[str]]:
    """从参数列表中提取 ``--lang <code>``，返回 ``(语言代码, 剩余参数)``。

    支持 ``--lang en_US`` 与 ``--lang=en_US`` 两种写法；未指定则返回 ``(None, argv)``。

    [EN] Extract ``--lang <code>`` from the argument list, returning
    ``(language code, remaining args)``. Supports both ``--lang en_US`` and
    ``--lang=en_US`` forms; returns ``(None, argv)`` if not specified.
    """
    lang: str | None = None
    remaining: list[str] = []
    skip_next = False
    for i, arg in enumerate(argv):
        if skip_next:
            skip_next = False
            continue
        if arg == "--lang":
            if i + 1 < len(argv):
                lang = argv[i + 1]
                skip_next = True
            continue
        if arg.startswith("--lang="):
            lang = arg.split("=", 1)[1]
            continue
        remaining.append(arg)
    return lang, remaining


def _apply_language(lang: str | None) -> None:
    """若指定了 ``--lang``，则调用 set_language 切换输出语言。

    [EN] If ``--lang`` is specified, call set_language to switch output language.
    """
    if lang is None:
        return
    try:
        from workflows.support.translations import set_language

        set_language(lang)
    except Exception:
        pass


def _requires_full_dependencies(mode: str, rest: list[str]) -> bool:
    """判断当前调用是否需要检查虚拟环境与完整依赖。

    Desktop 与 interactive 始终需要完整依赖；CLI 下的 help / print-example /
    workdir 可跳过。

    [EN] Whether the current invocation needs the full venv/dependency check.
    Desktop and interactive always do; for the CLI, help / print-example /
    workdir can be skipped.
    """
    if mode != "cli":
        return True
    if not rest:
        return True
    if rest[0] in _LIGHT_CLI_COMMANDS:
        return False
    if len(rest) >= 2 and rest[1] in {"--help", "-h"}:
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    """统一入口：引导 import 路径、按需检查依赖，并按模式分发。

    [EN] Unified entry point: bootstrap import paths, check dependencies as
    needed, and dispatch by mode.
    """
    _bootstrap_src_imports()
    # 保留 --lang 在原始 argv 中，使 ensure_runtime re-exec 后的新进程也能读取语言设置。
    # [EN] Keep --lang in the original argv so it survives ensure_runtime's re-exec.
    original = sys.argv[1:] if argv is None else list(argv)
    lang, rest = _extract_lang(original)
    _apply_language(lang)

    if not rest:
        mode = "desktop"
    elif rest[0] == "shell":
        mode = "shell"
    else:
        mode = "cli"

    if _requires_full_dependencies(mode, rest):
        try:
            _ensure_runtime(entry_script=ENTRY_SCRIPT, argv=original)
        except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
            print(
                _tr("cli_dependency_init_failed", "依赖初始化失败：{error}").format(error=exc),
                file=sys.stderr,
            )
            return 1

    if mode == "desktop":
        from desktop.application import main as run_desktop

        return run_desktop([])

    if mode == "shell":
        from workflows.interfaces.interactive_cli import main as run_interactive

        params_path = rest[1] if len(rest) > 1 and rest[1] not in {"--help", "-h"} else None
        return run_interactive(params_path)

    if rest and rest[0] in {"--help", "-h"}:
        from workflows.interfaces.interactive_cli import print_help

        print_help()
        return 0

    from workflows.interfaces.command_line import main as run_commands

    return run_commands(rest)


# ──────────────────────────────────────────────────────────────────────
# 虚拟环境与依赖管理（原 venv_and_deps.py）
# Venv & dependency management (formerly venv_and_deps.py)
# ──────────────────────────────────────────────────────────────────────


def _venv_python_path() -> Path:
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def _running_in_project_venv() -> bool:
    try:
        return Path(sys.prefix).resolve() == VENV_DIR.resolve()
    except OSError:
        return False


def _is_externally_managed_environment() -> bool:
    marker = Path(sysconfig.get_path("stdlib")) / "EXTERNALLY-MANAGED"
    return marker.is_file()


def _missing_requirements() -> list[str]:
    missing: list[str] = []
    for requirement, module_name in _REQUIRED_IMPORTS.items():
        try:
            available = importlib.util.find_spec(module_name) is not None
        except (ImportError, ModuleNotFoundError, ValueError):
            available = False
        if not available:
            missing.append(requirement)
    return missing


def _missing_requirements_for_python(python: Path) -> list[str]:
    proc = subprocess.run(
        [str(python), "-c", _CHECK_SCRIPT, json.dumps(_REQUIRED_IMPORTS)],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"Failed to detect dependencies: {python}")
    return json.loads(proc.stdout.strip() or "[]")


def _ensure_project_venv() -> Path:
    venv_python = _venv_python_path()
    if venv_python.is_file():
        return venv_python
    print(f"Creating project virtual environment: {VENV_DIR}")
    subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)], check=True)
    if not venv_python.is_file():
        raise RuntimeError(f"Failed to create virtual environment: {venv_python}")
    return venv_python


def _resolve_install_python() -> Path:
    if _running_in_project_venv():
        return Path(sys.executable)
    if _is_externally_managed_environment():
        return _ensure_project_venv()
    if _venv_python_path().is_file():
        return _venv_python_path()
    return Path(sys.executable)


def _pip_install(python: Path) -> None:
    subprocess.run(
        [str(python), "-m", "pip", "install", "-r", str(REQUIREMENTS_FILE)],
        check=True,
    )


def _different_executable_path(left: Path, right: Path) -> bool:
    # Do not resolve symlinks here: venv/bin/python often points to the
    # Homebrew interpreter, but executing through that path still activates
    # the virtual environment via sys.prefix.
    return left.absolute() != right.absolute()


def _reexec(python: Path, entry_script: Path, argv: list[str]) -> None:
    args = [str(python), str(entry_script), *argv]
    os.execv(str(python), args)


def _ensure_dependencies(*, quiet: bool = False) -> Path | None:
    """Install missing dependencies. Returns venv python when caller must re-exec."""
    missing = _missing_requirements()
    if not missing:
        if not quiet:
            print("Dependency check passed.")
        return None

    if not REQUIREMENTS_FILE.is_file():
        raise RuntimeError(f"Requirements file not found: {REQUIREMENTS_FILE}")

    print("Missing dependencies, installing automatically: " + ", ".join(missing))
    install_python = _resolve_install_python()
    try:
        _pip_install(install_python)
    except subprocess.CalledProcessError:
        if _different_executable_path(install_python, Path(sys.executable)):
            raise
        install_python = _ensure_project_venv()
        _pip_install(install_python)

    if _different_executable_path(install_python, Path(sys.executable)):
        return install_python

    remaining = _missing_requirements()
    if remaining:
        raise RuntimeError("Still unimportable after installation: " + ", ".join(remaining))
    print("Dependencies installed.")
    return None


def _ensure_runtime(*, entry_script: Path, argv: list[str] | None = None) -> None:
    """Ensure dependencies and re-exec into the project venv when needed."""
    argv = list(argv or [])
    venv_python = _venv_python_path()

    if venv_python.is_file() and not _running_in_project_venv():
        print(f"Using project virtual environment: {VENV_DIR}")
        _reexec(venv_python, entry_script, argv)

    reexec_python = _ensure_dependencies()
    if reexec_python is not None:
        print(f"Switched to project virtual environment: {VENV_DIR}")
        _reexec(reexec_python, entry_script, argv)

    if _missing_requirements():
        raise RuntimeError("Still unimportable after installation: " + ", ".join(_missing_requirements()))


if __name__ == "__main__":
    raise SystemExit(main())
